"""Prepared actions for project lifecycle, project libraries, and Media Pool state."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import base64
from hashlib import sha256
import json
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping

from ..connection import get_connection
from ..core import media_pool, project_library_ops, project_ops, render_engine, sdk_live_inspection
from ..errors import APICallFailed, ValidationError
from ..runtime_health import close_current_project_with_runtime_health
from .project_render_storage_media_prepared_action import (
    _assert_native_project_binding,
    _assert_public,
    _canonical,
    _digest,
    _evidence,
    _impact,
    _native_library_identity,
    _project_binding,
    _project_protected_state,
    _target,
)


_CAPABILITY_IDS = {
    "cutagent.action.media.folders.create": "media.folder_management",
    "cutagent.action.media.folders.delete": "media.folder_move_delete",
    "cutagent.action.media.metadata": "media.metadata_write",
    "cutagent.action.media.property_set": "media.metadata_write",
    "cutagent.action.media.third_party_metadata.set": "media.metadata_write",
    "cutagent.action.project.archive": "project.archive_restore",
    "cutagent.action.project.cleanup_scratch": "project.cleanup_scratch",
    "cutagent.action.project.close": "project.close",
    "cutagent.action.project.cloud.create": "project.cloud.create",
    "cutagent.action.project.cloud.import": "project.cloud.import",
    "cutagent.action.project.cloud.open": "project.cloud.open",
    "cutagent.action.project.cloud.restore": "project.cloud.restore",
    "cutagent.action.project.delete": "project.delete",
    "cutagent.action.project.export": "project.export_drp",
    "cutagent.action.project.folders.create": "project.folder_management",
    "cutagent.action.project.folders.delete": "project.folder_management",
    "cutagent.action.project.folders.open": "project.folder_management",
    "cutagent.action.project.folders.root": "project.folder_management",
    "cutagent.action.project.folders.up": "project.folder_management",
    "cutagent.action.project.import": "project.import_drp",
    "cutagent.action.project.library.backup": "project.library_backup",
    "cutagent.action.project.library.create": "project.library_create",
    "cutagent.action.project.library.restore": "project.library_restore",
    "cutagent.action.project.library.switch": "project.library_switch",
    "cutagent.action.project.open": "project.open",
    "cutagent.action.project.preset.load": "project.preset_load",
    "cutagent.action.project.preset.save": "project.preset_save",
    "cutagent.action.project.restore": "project.archive_restore",
    "cutagent.action.project.save": "project.settings_write",
    "cutagent.action.render.burnin.export": "render.burnin_preset_import_export",
    "cutagent.action.render.burnin.import": "render.burnin_preset_import_export",
    "cutagent.action.render.export_preset": "render.preset_import_export",
    "cutagent.action.render.import_preset": "render.preset_import_export",
}
_ARTIFACT_ID = re.compile(r"^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$")
_PROJECT_ARTIFACT_INPUTS = {
    "cutagent.action.project.export": ("destinationArtifactId", False, False),
    "cutagent.action.project.library.backup": ("destinationArtifactId", False, True),
    "cutagent.action.project.library.restore": ("sourceArtifactId", True, True),
    "cutagent.action.project.restore": ("sourceArtifactId", True, True),
    "cutagent.action.project.import": ("sourceArtifactId", True, False),
}
_CLOUD_ARTIFACT_INPUTS = {
    "cutagent.action.project.cloud.import": ("sourceArtifactId", False),
    "cutagent.action.project.cloud.restore": ("sourceArtifactId", True),
}
_PROJECT_MANAGER_CUSTODY_ACTION_IDS = frozenset({
    "cutagent.action.project.archive", "cutagent.action.project.cleanup_scratch",
    "cutagent.action.project.delete", "cutagent.action.project.export",
    "cutagent.action.project.open", "cutagent.action.project.folders.create",
    "cutagent.action.project.folders.delete", "cutagent.action.project.folders.open",
    "cutagent.action.project.folders.root", "cutagent.action.project.folders.up",
    "cutagent.action.project.import", "cutagent.action.project.restore",
})
_PROJECT_LIBRARY_CUSTODY_ACTION_IDS = frozenset({
    "cutagent.action.project.library.backup",
    "cutagent.action.project.library.create",
    "cutagent.action.project.library.restore",
    "cutagent.action.project.library.switch",
})
_VERIFIED_PROJECT_INTERNAL_ACTIONS = frozenset({
    "cutagent.action.project.preset.load",
    "cutagent.action.project.preset.save",
    "cutagent.action.project.save",
})
_UNSET_NATIVE_ID = object()


def _opaque(prefix: str, value: str) -> str:
    return f"{prefix}{sha256(value.encode()).hexdigest()[:32]}"


def _sdk_native_id(prefix: str, project_id: str, native_id: str) -> str:
    return _sdk_digest(prefix, {"nativeId": native_id, "projectId": project_id})


def _sdk_digest(prefix: str, value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    encoded = base64.urlsafe_b64encode(sha256(payload).digest()).rstrip(b"=").decode()
    return f"{prefix}f{encoded}"


def _text_object(value: Any, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not set(value) <= set(required) | set(optional):
        raise ValidationError("Prepared action input has unexpected fields.")
    if any(not isinstance(value.get(key), str) or not value[key].strip() for key in required):
        raise ValidationError("Prepared action required text fields must be non-empty strings.")
    result = {key: value[key].strip() if isinstance(value[key], str) else value[key] for key in value}
    if any(isinstance(item, str) and len(item) > (4096 if "path" in key.lower() else 1024) for key, item in result.items()):
        raise ValidationError("Prepared action input exceeded its public contract limit.")
    return result


def _literal_text(value: Any, *, maximum: int | None = None) -> str:
    """Validate a caller-owned value without trimming or rejecting emptiness."""

    if not isinstance(value, str) or (maximum is not None and len(value) > maximum):
        raise ValidationError("Prepared action value exceeded its public text contract.")
    return value


def _absolute_path(value: str, *, must_exist: bool, destination: bool = False) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValidationError("Prepared artifact paths must be absolute.")
    path = path.resolve(strict=must_exist)
    if must_exist and not path.exists():
        raise ValidationError("Prepared action source path does not exist.")
    if destination and path.exists():
        raise ValidationError("Prepared action destination already exists; overwrite is forbidden.")
    if destination and not path.parent.is_dir():
        raise ValidationError("Prepared action destination parent does not exist.")
    return str(path)


def _managed_artifact_path(
    context: Mapping[str, Any],
    artifact_id: str,
    *,
    existing: bool,
    directory: bool,
) -> str:
    if not isinstance(artifact_id, str) or _ARTIFACT_ID.fullmatch(artifact_id) is None:
        raise ValidationError("Prepared artifact identity is invalid.")
    bindings = context.get("privateBindings")
    records = bindings.get("privateManagedArtifacts") if isinstance(bindings, Mapping) else None
    record = records.get(artifact_id) if isinstance(records, Mapping) else None
    path_value = record.get("path") if isinstance(record, Mapping) else None
    root_value = bindings.get("privateArtifactStoreRoot") if isinstance(bindings, Mapping) else None
    if not isinstance(path_value, str) or not isinstance(root_value, str):
        raise ValidationError("Prepared artifact is not in carrier-managed custody.")
    root = Path(root_value).expanduser().resolve(strict=True)
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        raise ValidationError("Carrier-managed artifact path is invalid.")
    if path.is_symlink():
        raise ValidationError("Carrier-managed artifact path cannot be a symbolic link.")
    resolved = path.resolve(strict=existing)
    if resolved == root or root not in resolved.parents:
        raise ValidationError("Carrier-managed artifact escaped its private root.")
    if existing:
        valid = resolved.is_dir() if directory else resolved.is_file()
        if not valid or resolved.is_symlink():
            raise ValidationError("Carrier-managed source artifact is unavailable.")
        expected = record.get("contentTreeDigest" if directory else "sha256")
        if directory and expected is None:
            expected = record.get("treeDigest")
        if not isinstance(expected, str):
            raise ValidationError("Carrier-managed source artifact has no authenticated digest.")
        actual = _artifact_content_digest(resolved)
        if expected.removeprefix("sha256:") != actual:
            raise ValidationError("Carrier-managed source artifact digest changed.")
    else:
        if not isinstance(record.get("reservationId"), str) or not record["reservationId"]:
            raise ValidationError("Carrier-managed destination has no reservation.")
        if not resolved.parent.is_dir():
            raise ValidationError("Carrier-managed destination parent is unavailable.")
        if directory:
            if not resolved.is_dir() or resolved.is_symlink() or any(resolved.iterdir()):
                raise ValidationError("Carrier-managed destination directory is no longer fresh.")
        elif not resolved.is_file() or resolved.is_symlink() or resolved.stat().st_size != 0:
            raise ValidationError("Carrier-managed destination file is no longer fresh.")
    return str(resolved)


def _artifact_content_digest(path: Path) -> str:
    if path.is_symlink():
        raise ValidationError("Carrier-managed artifacts cannot contain symbolic links.")
    if path.is_file():
        return sha256(path.read_bytes()).hexdigest()
    if not path.is_dir():
        raise ValidationError("Carrier-managed source artifact is unavailable.")
    digest = sha256()
    for child in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        relative = child.relative_to(path).as_posix().encode()
        if child.is_symlink():
            raise ValidationError("Carrier-managed artifacts cannot contain symbolic links.")
        if child.is_dir():
            digest.update(b"directory\0" + relative + b"\0")
        elif child.is_file():
            digest.update(b"file\0" + relative + b"\0")
            digest.update(sha256(child.read_bytes()).digest())
        else:
            raise ValidationError("Carrier-managed artifacts contain an unsupported entry.")
    return digest.hexdigest()


def _native_id(target: Any, *, prefix: str, fallback: str) -> str:
    for method_name in ("GetUniqueId", "GetUniqueID", "GetId", "GetID", "GetMediaId"):
        getter = getattr(target, method_name, None)
        if callable(getter):
            value = getter()
            if value not in (None, ""):
                return _opaque(prefix, str(value))
    return _opaque(prefix, fallback)


def _native_token(target: Any) -> str | None:
    for method_name in ("GetUniqueId", "GetUniqueID", "GetId", "GetID", "GetMediaId"):
        getter = getattr(target, method_name, None)
        if callable(getter):
            value = getter()
            if value not in (None, ""):
                return str(value)
    return None


def _walk_media_folders(folder: Any, parent_path: str = ""):
    name = folder.GetName()
    path = f"{parent_path}/{name}".strip("/")
    yield folder, path
    for child in folder.GetSubFolderList() or []:
        yield from _walk_media_folders(child, path)


def _folder_by_public_id(conn: Any, project_id: str, public_id: str) -> tuple[Any, str]:
    matches = []
    for folder, path in _walk_media_folders(conn.media_pool.GetRootFolder()):
        native_id = _native_token(folder)
        if native_id and _sdk_native_id("media_pool_folder_", project_id, native_id) == public_id:
            matches.append((folder, path))
    if len(matches) != 1:
        raise ValidationError("The durable Media Pool folder identity is missing or ambiguous.")
    return matches[0]


def _clip_by_public_id(conn: Any, project_id: str, public_id: str) -> tuple[Any, str]:
    matches = []
    for folder, path in _walk_media_folders(conn.media_pool.GetRootFolder()):
        for clip in folder.GetClipList() or []:
            native_id = sdk_live_inspection.media_pool_native_id(clip)
            if native_id and _sdk_native_id("media_pool_item_", project_id, native_id) == public_id:
                matches.append((clip, path))
    if len(matches) != 1:
        raise ValidationError("The durable Media Pool asset identity is missing or ambiguous.")
    return matches[0]


def _active_context(conn: Any, context: Mapping[str, Any]) -> dict[str, Any]:
    project = getattr(conn, "project", None)
    timeline = getattr(conn, "timeline", None)
    if project is None:
        project_result = None
        timeline_result = None
    else:
        signed, _ = _project_binding(context)
        name = project.GetName()
        project_id = signed["projectId"] if name == signed.get("projectName") else _native_id(
            project, prefix="project_", fallback=name
        )
        project_result = {"id": project_id, "name": name}
        timeline_result = None
        if timeline is not None and callable(getattr(timeline, "GetName", None)):
            timeline_result = {
                "id": _native_id(timeline, prefix="timeline_", fallback=f"{project_id}:{timeline.GetName()}"),
                "projectId": project_id,
                "name": timeline.GetName(),
            }
    return {"project": project_result, "timeline": timeline_result, "matchedAfterMutation": True}


def _semantic_context(
    conn: Any,
    context: Mapping[str, Any],
    *,
    project_id: str | None = None,
    timeline_native_id: str | None | object = _UNSET_NATIVE_ID,
) -> dict[str, Any]:
    active = _active_context(conn, context)
    if project_id is not None and active["project"] is not None:
        active["project"] = {**active["project"], "id": project_id}
        if active["timeline"] is not None:
            if timeline_native_id is not _UNSET_NATIVE_ID:
                current_native_id = _native_token(getattr(conn, "timeline", None))
                if not current_native_id or timeline_native_id != current_native_id:
                    raise ValidationError(
                        "The active timeline identity changed after the prepared project-open execution."
                    )
                active["timeline"] = {
                    **active["timeline"],
                    "id": _sdk_native_id("timeline_", project_id, current_native_id),
                    "projectId": project_id,
                }
            else:
                active["timeline"] = {**active["timeline"], "projectId": project_id}
        elif timeline_native_id is not _UNSET_NATIVE_ID and timeline_native_id is not None:
            raise ValidationError(
                "The prepared project-open timeline identity has no active timeline readback."
            )
    database = _database(conn)
    return {
        "library": {"name": database["DbName"], "kind": str(database["DbType"]).lower()},
        "project": active["project"],
        "timeline": (
            None
            if active["timeline"] is None
            else {"id": active["timeline"]["id"], "name": active["timeline"]["name"]}
        ),
        "projectRevision": {"status": "unavailable"},
    }


def _database(conn: Any) -> dict[str, Any]:
    getter = getattr(conn.project_manager, "GetCurrentDatabase", None)
    value = getter() if callable(getter) else None
    if not isinstance(value, Mapping) or not value.get("DbName") or not value.get("DbType"):
        raise APICallFailed("DaVinci Resolve did not expose the current project-library identity.")
    return {key: value[key] for key in ("DbType", "DbName", "IpAddress") if key in value}


def _refresh(conn: Any) -> None:
    refresh = getattr(conn, "refresh", None)
    if callable(refresh):
        refresh()
    manager = conn.project_manager
    getter = getattr(manager, "GetCurrentProject", None)
    if callable(getter):
        conn.project = getter()
        timeline_getter = getattr(conn.project, "GetCurrentTimeline", None) if conn.project else None
        conn.timeline = timeline_getter() if callable(timeline_getter) else None


def _project_names_in_current_folder(conn: Any) -> list[str]:
    getter = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
    projects = getter() if callable(getter) else None
    if not isinstance(projects, list):
        raise APICallFailed("DaVinci Resolve project-list readback is unavailable.")
    return [str(project) for project in projects]


def _current_project_name(conn: Any) -> str | None:
    project = getattr(conn, "project", None)
    getter = getattr(project, "GetName", None) if project is not None else None
    if project is None:
        return None
    name = str(getter() or "").strip() if callable(getter) else ""
    if not name:
        raise APICallFailed("DaVinci Resolve current-project readback is unavailable.")
    return name


def _is_unlisted_project_manager_placeholder(conn: Any, active: str | None) -> bool:
    if active != "Untitled Project" or getattr(conn, "timeline", None) is not None:
        return False
    project = getattr(conn, "project", None)
    timeline_count_getter = getattr(project, "GetTimelineCount", None)
    project_list_getter = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
    if project is None or not callable(timeline_count_getter) or not callable(project_list_getter):
        return False
    try:
        timeline_count = int(timeline_count_getter() or 0)
        projects = project_list_getter()
    except Exception:
        return False
    return timeline_count == 0 and isinstance(projects, list) and active not in projects


def _wait_for_project_deleted(conn: Any, name: str, *, existed_before: bool) -> bool:
    if not existed_before:
        return False
    for attempt in range(6):
        if name not in set(_project_names_in_current_folder(conn)):
            return True
        if attempt < 5:
            _refresh(conn)
            time.sleep(0.1)
    return False


def _artifact(path: str, *, directory: bool = False) -> dict[str, Any]:
    item = Path(path)
    exists = item.is_dir() if directory else item.is_file()
    if not exists:
        raise APICallFailed("The expected artifact was not found after mutation.")
    stat = item.stat()
    return {"path": str(item), "size": stat.st_size, "mtimeNs": str(stat.st_mtime_ns), "directory": directory}


def _project_target(context: Mapping[str, Any], name: str) -> dict[str, Any]:
    project, _ = _project_binding(context)
    stable = project["projectId"] if name == project.get("projectName") else _opaque("project_", f"{project['projectLibraryId']}:{name}")
    return {"kind": "project", "stableId": stable, "revision": _digest({"library": project["projectLibraryId"], "name": name})}


def _library_target(context: Mapping[str, Any], name: str) -> dict[str, Any]:
    project, _ = _project_binding(context)
    stable = _opaque("project_library_", f"{project['projectLibraryId']}:{name}")
    return {"kind": "project_library", "stableId": stable, "revision": _digest({"name": name, "kind": "disk"})}


def _folder_target(context: Mapping[str, Any], name: str) -> dict[str, Any]:
    project, _ = _project_binding(context)
    stable = _opaque("project_folder_", f"{project['projectLibraryId']}:{name}")
    return {"kind": "project_folder", "stableId": stable, "revision": _digest({"library": project["projectLibraryId"], "name": name})}


def _carrier_array(value: Any) -> list[Any] | None:
    """Copy a JSON array from either mutable tests or authority-frozen custody."""
    return list(value) if isinstance(value, (list, tuple)) else None


def _signed_artifact_targets(
    context: Mapping[str, Any], primary: Mapping[str, Any], artifact_id: str
) -> list[dict[str, Any]]:
    exact = context.get("exactRequestBinding")
    identities = exact.get("identities") if isinstance(exact, Mapping) else None
    revisions = exact.get("revisions") if isinstance(exact, Mapping) else None
    target_ids = _carrier_array(identities.get("targetIds")) if isinstance(identities, Mapping) else None
    target_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
    if (
        target_ids is None
        or len(target_ids) != 2
        or target_ids[1] != artifact_id
        or not isinstance(target_revisions, Mapping)
        or set(target_revisions) != set(target_ids)
        or any(not isinstance(target_revisions.get(target_id), str) for target_id in target_ids)
    ):
        raise ValidationError(
            "Prepared Project artifact targets drifted from carrier-owned custody."
        )
    return [
        {**dict(primary), "stableId": target_ids[0], "revision": target_revisions[target_ids[0]]},
        {"kind": "artifact", "stableId": artifact_id, "revision": target_revisions[artifact_id]},
    ]


def _signed_primary_target(
    context: Mapping[str, Any], primary: Mapping[str, Any]
) -> dict[str, Any]:
    exact = context.get("exactRequestBinding")
    identities = exact.get("identities") if isinstance(exact, Mapping) else None
    revisions = exact.get("revisions") if isinstance(exact, Mapping) else None
    target_ids = _carrier_array(identities.get("targetIds")) if isinstance(identities, Mapping) else None
    target_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
    if (
        target_ids is None
        or len(target_ids) != 1
        or not isinstance(target_revisions, Mapping)
        or set(target_revisions) != set(target_ids)
        or not isinstance(target_revisions.get(target_ids[0]), str)
    ):
        raise ValidationError("Prepared Project target drifted from carrier-owned custody.")
    return {
        **dict(primary),
        "stableId": target_ids[0],
        "revision": target_revisions[target_ids[0]],
    }


def _assert_signed_targets(
    context: Mapping[str, Any], targets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    exact = context.get("exactRequestBinding")
    identities = exact.get("identities") if isinstance(exact, Mapping) else None
    revisions = exact.get("revisions") if isinstance(exact, Mapping) else None
    target_ids = _carrier_array(identities.get("targetIds")) if isinstance(identities, Mapping) else None
    target_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
    expected_ids = [target["stableId"] for target in targets]
    expected_revisions = {target["stableId"]: target["revision"] for target in targets}
    if target_ids != expected_ids or target_revisions != expected_revisions:
        raise ValidationError("Prepared Project targets drifted from carrier-owned custody.")
    return targets


def _current_project_manager_custody(
    context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]
) -> dict[str, Any]:
    project_open = action_id == "cutagent.action.project.open"
    conn = get_connection(require_project=not project_open)
    if project_open:
        project, _ = _project_binding(context)
        native_project_id = project.get("nativeProjectId")
        native_library = project.get("nativeProjectLibrary")
        if (
            not isinstance(native_project_id, str)
            or not native_project_id
            or not isinstance(native_library, Mapping)
            or _native_library_identity(conn) != dict(native_library)
        ):
            raise ValidationError(
                "The exact DaVinci Resolve project library or Project Manager target changed."
            )
        native = {
            "projectId": project["projectId"],
            "nativeProjectId": native_project_id,
            "projectLibraryId": project["projectLibraryId"],
            "nativeProjectLibrary": dict(native_library),
        }
    else:
        native = _assert_native_project_binding(context, conn)
    raw = project_library_ops.current_project_folder_identity(conn)
    if not isinstance(raw, Mapping):
        raise ValidationError("The exact native Project Manager folder is unavailable.")
    current_folder = {"path": raw.get("path"), "nativeId": raw.get("native_id")}
    children = sorted(
        ({"name": row.get("name"), "path": row.get("path"), "nativeId": row.get("native_id")} for row in raw.get("children", [])),
        key=lambda row: str(row["path"]),
    )
    ancestors = sorted(
        ({"path": row.get("path"), "nativeId": row.get("native_id")} for row in raw.get("ancestors", [])),
        key=lambda row: str(row["path"]),
    )
    listed = conn.project_manager.GetProjectListInCurrentFolder()
    if not isinstance(listed, list) or any(not isinstance(name, str) for name in listed):
        raise ValidationError("The exact native Project Manager inventory is unavailable.")
    raw_project_records = raw.get("project_records")
    bindings = context.get("privateBindings")
    expected = bindings.get("projectManager") if isinstance(bindings, Mapping) else None
    expected_projects = expected.get("projects") if isinstance(expected, Mapping) else None
    if (
        not isinstance(raw_project_records, list)
        or not isinstance(expected_projects, (list, tuple))
        or len(raw_project_records) != len(listed)
        or len(expected_projects) != len(listed)
    ):
        raise ValidationError("The exact native Project Manager project identities are unavailable.")
    native_by_name = {
        row.get("name"): row.get("native_id")
        for row in raw_project_records
        if isinstance(row, Mapping)
        and isinstance(row.get("name"), str)
        and isinstance(row.get("native_id"), str)
        and row.get("native_id")
    }
    expected_by_name = {
        row.get("name"): row
        for row in expected_projects
        if isinstance(row, Mapping) and isinstance(row.get("name"), str)
    }
    if (
        len(native_by_name) != len(listed)
        or len(set(native_by_name.values())) != len(listed)
        or len(expected_by_name) != len(listed)
        or set(native_by_name) != set(listed)
        or set(expected_by_name) != set(listed)
    ):
        raise ValidationError("The native Project Manager project identities are incomplete or ambiguous.")
    projects = []
    for index, name in enumerate(listed, start=1):
        current = (
            name == _current_project_name(conn)
            and raw.get("open_project_native_id") == native_by_name[name]
        )
        expected_row = expected_by_name[name]
        if (
            expected_row.get("nativeId") != native_by_name[name]
            or expected_row.get("current") is not current
            or expected_row.get("index") != index
            or not isinstance(expected_row.get("id"), str)
            or not expected_row["id"]
        ):
            raise ValidationError("The signed Project Manager project identity changed.")
        projects.append({
            "id": expected_row["id"], "name": name, "current": current,
            "index": index, "nativeId": native_by_name[name],
        })
    projects.sort(key=lambda row: row["name"].encode())
    inventory_revision = _digest({
        "projectLibraryId": native["projectLibraryId"], "nativeProjectLibrary": native["nativeProjectLibrary"], "currentFolder": current_folder,
        "children": children, "projects": projects, "ancestors": ancestors,
    })
    if action_id.startswith("cutagent.action.project.folders."):
        parts = str(current_folder["path"]).split(" / ")
        path = str(current_folder["path"])
        native_id = current_folder["nativeId"]
        state = "existing"
        if action_id.endswith(".root"):
            path = "Projects"
        elif action_id.endswith(".up"):
            path = " / ".join(parts[:-1]) if len(parts) > 1 else "Projects"
        else:
            path = f"{current_folder['path']} / {value['name']}"
        if action_id.endswith(".create"):
            if any(row["path"] == path for row in children):
                raise ValidationError("The exact project folder is no longer absent.")
            native_id = None
            state = "absent"
        elif action_id.endswith((".root", ".up")):
            matches = [row for row in ancestors if row["path"] == path]
            if len(matches) != 1:
                raise ValidationError("The exact Project Manager ancestor changed.")
            native_id = matches[0]["nativeId"]
        else:
            matches = [row for row in children if row["path"] == path and row["name"] == value["name"]]
            if len(matches) != 1:
                raise ValidationError("The exact Project Manager folder target changed.")
            native_id = matches[0]["nativeId"]
        stable_id = _opaque("project_folder_", f"{native['projectLibraryId']}:{path}")
        targets = [{"kind": "project_folder", "stableId": stable_id,
                    "revision": _digest({"inventoryRevision": inventory_revision, "actionId": action_id, "path": path, "nativeId": native_id, "state": state}),
                    "path": path, "nativeId": native_id, "state": state}]
    elif action_id in {"cutagent.action.project.import", "cutagent.action.project.restore"}:
        name = value.get("name")
        if not isinstance(name, str) or not name or any(row["name"] == name for row in projects):
            raise ValidationError("The exact Project import/restore target is no longer absent.")
        stable_id = _sdk_digest("project_", {
            "projectLibraryId": native["projectLibraryId"],
            "projectFolderId": current_folder["nativeId"],
            "name": name,
        })
        targets = [{
            "kind": "project", "stableId": stable_id,
            "revision": _digest({"inventoryRevision": inventory_revision, "actionId": action_id, "name": name, "state": "absent"}),
            "name": name, "state": "absent",
        }]
    else:
        if action_id.endswith("cleanup_scratch"):
            names = [row["name"] for row in projects if not row["current"] and any(row["name"].startswith(prefix) for prefix in value["prefixes"])]
            if not names or len(names) > value["limit"]:
                raise ValidationError("The exact scratch project inventory changed.")
        else:
            names = [value["name"]]
        targets = []
        for name in names:
            matches = [row for row in projects if row["name"] == name]
            if len(matches) != 1 or (action_id.endswith(".delete") and matches[0]["current"]):
                raise ValidationError("The exact Project Manager project target changed.")
            row = matches[0]
            targets.append({**row, "kind": "project", "stableId": row["id"],
                            "revision": _digest({"inventoryRevision": inventory_revision, "actionId": action_id, "project": row})})
    actual = {
        "projectLibraryId": native["projectLibraryId"], "nativeProjectLibrary": native["nativeProjectLibrary"], "currentFolder": current_folder,
        "children": children, "projects": projects, "ancestors": ancestors,
        "inventoryRevision": inventory_revision, "targets": targets,
    }
    return actual


def _project_manager_custody(
    context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]
) -> dict[str, Any]:
    bindings = context.get("privateBindings")
    expected = bindings.get("projectManager") if isinstance(bindings, Mapping) else None
    if not isinstance(expected, Mapping):
        raise ValidationError("Prepared Project Manager custody is missing.")
    actual = _current_project_manager_custody(context, action_id, value)
    if _canonical(actual) != _canonical(expected):
        raise ValidationError("The exact Project Manager inventory or folder custody changed.")
    exact = context.get("exactRequestBinding")
    identities = exact.get("identities") if isinstance(exact, Mapping) else None
    revisions = exact.get("revisions") if isinstance(exact, Mapping) else None
    target_ids = _carrier_array(identities.get("targetIds")) if isinstance(identities, Mapping) else None
    target_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
    expected_ids = [target["stableId"] for target in actual["targets"]]
    artifact_action = action_id in {
        "cutagent.action.project.archive",
        "cutagent.action.project.export",
        "cutagent.action.project.import",
        "cutagent.action.project.restore",
    }
    if (
        target_ids is None
        or (
            target_ids[:len(expected_ids)] != expected_ids
            if artifact_action
            else target_ids != expected_ids
        )
        or not isinstance(target_revisions, Mapping)
        or (not artifact_action and set(target_revisions) != set(expected_ids))
        or any(target_revisions.get(target["stableId"]) != target["revision"] for target in actual["targets"])
    ):
        raise ValidationError("Prepared Project Manager targets drifted from carrier-owned custody.")
    return actual


def _native_library_from_database(database: Mapping[str, Any]) -> dict[str, str]:
    db_type = database.get("DbType")
    db_name = database.get("DbName")
    if db_type not in {"Disk", "PostgreSQL"} or not isinstance(db_name, str) or not db_name:
        raise ValidationError("The native project-library identity is incomplete.")
    native = {"name": db_name, "kind": str(db_type).lower()}
    if db_type == "PostgreSQL":
        address = database.get("IpAddress")
        if not isinstance(address, str) or not address:
            raise ValidationError("The PostgreSQL project-library address is unavailable.")
        native["address"] = address
    return native


def _current_project_library_custody(
    context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]
) -> dict[str, Any]:
    bindings = context.get("privateBindings")
    expected = bindings.get("projectLibraries") if isinstance(bindings, Mapping) else None
    expected_rows = _carrier_array(expected.get("databases")) if isinstance(expected, Mapping) else None
    if not isinstance(expected, Mapping) or expected_rows is None:
        raise ValidationError("Prepared project-library inventory custody is missing.")
    conn = get_connection(require_project=False)
    inventory = project_library_ops.project_library_inventory_identity(conn)
    databases = []
    for database in inventory["databases"]:
        matches = [
            row for row in expected_rows
            if isinstance(row, Mapping) and _canonical(row.get("database")) == _canonical(database)
        ]
        if len(matches) != 1:
            raise ValidationError("The exact native project-library inventory changed.")
        expected_row = matches[0]
        native = _native_library_from_database(database)
        if _canonical(expected_row.get("nativeProjectLibrary")) != _canonical(native):
            raise ValidationError("The native project-library projection changed.")
        stable_id = expected_row.get("stableId")
        if not isinstance(stable_id, str) or not stable_id:
            raise ValidationError("The project-library stable identity is unavailable.")
        databases.append({
            "stableId": stable_id,
            "nativeProjectLibrary": native,
            "database": dict(database),
        })
    databases.sort(
        key=lambda row: json.dumps(
            _canonical(row["database"]), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    )
    if len(databases) != len(expected_rows):
        raise ValidationError("The exact native project-library inventory changed.")
    current_database = inventory["current_database"]
    inventory_revision = _digest({"currentDatabase": current_database, "databases": databases})
    name = value.get("libraryName")
    matches = [
        row for row in databases
        if row["database"].get("DbType") == "Disk" and row["database"].get("DbName") == name
    ]
    if action_id in {
        "cutagent.action.project.library.create",
        "cutagent.action.project.library.restore",
    }:
        if matches:
            raise ValidationError("The prepared Disk project-library destination name already exists.")
        destination = _project_library_destination(context, value)
        if destination["namespaceRevision"] != inventory_revision:
            raise ValidationError("The exact project-library namespace changed after destination reservation.")
        target = {
            "kind": "project_library",
            "stableId": destination["libraryDestinationId"],
            "revision": _digest({
                "inventoryRevision": inventory_revision,
                "actionId": action_id,
                "libraryName": name,
                "absenceRevision": destination["absenceRevision"],
            }),
            "database": {"DbType": "Disk", "DbName": name},
            "destinationId": destination["libraryDestinationId"],
        }
        return {
            "currentDatabase": current_database,
            "databases": databases,
            "inventoryRevision": inventory_revision,
            "target": target,
        }
    if len(matches) != 1:
        raise ValidationError("The exact Disk project-library target is missing or ambiguous.")
    selected = matches[0]
    target = {
        "kind": "project_library",
        "stableId": selected["stableId"],
        "revision": _digest({"inventoryRevision": inventory_revision, "actionId": action_id, "database": selected["database"]}),
        "database": dict(selected["database"]),
    }
    return {
        "currentDatabase": current_database,
        "databases": databases,
        "inventoryRevision": inventory_revision,
        "target": target,
    }


def _project_library_destination(
    context: Mapping[str, Any], value: Mapping[str, Any]
) -> dict[str, Any]:
    bindings = context.get("privateBindings")
    destination = bindings.get("projectLibraryDestination") if isinstance(bindings, Mapping) else None
    required = {
        "libraryDestinationId", "operationId", "accountFingerprint", "libraryName",
        "managedRootId", "canonicalRootPath", "canonicalParentPath", "parentIdentity",
        "leafName", "canonicalFinalPath", "namespaceRevision", "absenceRevision", "state",
    }
    if not isinstance(destination, Mapping) or set(destination) != required:
        raise ValidationError("Prepared project-library destination custody is missing or malformed.")
    exact = context.get("exactRequestBinding")
    if (
        destination.get("state") != "reserved"
        or destination.get("libraryName") != value.get("libraryName")
        or not isinstance(exact, Mapping)
        or destination.get("operationId") != exact.get("operationId")
        or Path(str(value.get("directoryPath"))).resolve() != Path(str(destination.get("canonicalFinalPath")))
    ):
        raise ValidationError("Prepared project-library destination ownership changed.")
    parent = Path(str(destination["canonicalParentPath"]))
    final = Path(str(destination["canonicalFinalPath"]))
    root = Path(str(destination["canonicalRootPath"]))
    try:
        parent_stat = parent.lstat()
    except OSError as error:
        raise ValidationError("Prepared project-library destination parent is unavailable.") from error
    expected_identity = destination["parentIdentity"]
    if (
        not isinstance(expected_identity, Mapping)
        or parent.is_symlink() or not parent.is_dir()
        or parent.resolve() != parent or root.resolve() != root or parent != root
        or final.parent != parent or final.name != destination["leafName"]
        or str(parent_stat.st_dev) != expected_identity.get("device")
        or str(parent_stat.st_ino) != expected_identity.get("inode")
        or final.exists() or final.is_symlink()
    ):
        raise ValidationError("Prepared project-library destination absence or root identity changed.")
    return dict(destination)


def _project_library_custody(
    context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]
) -> dict[str, Any]:
    bindings = context.get("privateBindings")
    expected = bindings.get("projectLibraries") if isinstance(bindings, Mapping) else None
    if not isinstance(expected, Mapping):
        raise ValidationError("Prepared project-library custody is missing.")
    actual = _current_project_library_custody(context, action_id, value)
    if _canonical(actual) != _canonical(expected):
        raise ValidationError("The exact project-library inventory custody changed.")
    exact = context.get("exactRequestBinding")
    identities = exact.get("identities") if isinstance(exact, Mapping) else None
    revisions = exact.get("revisions") if isinstance(exact, Mapping) else None
    target_ids = _carrier_array(identities.get("targetIds")) if isinstance(identities, Mapping) else None
    target_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
    target = actual["target"]
    artifact_action = action_id in {
        "cutagent.action.project.library.backup",
        "cutagent.action.project.library.restore",
    }
    if (
        target_ids is None
        or (target_ids[0] if target_ids else None) != target["stableId"]
        or (not artifact_action and target_ids != [target["stableId"]])
        or not isinstance(target_revisions, Mapping)
        or target_revisions.get(target["stableId"]) != target["revision"]
        or (not artifact_action and set(target_revisions) != {target["stableId"]})
    ):
        raise ValidationError("Prepared project-library targets drifted from carrier-owned custody.")
    return actual


_PUBLIC_IMPACT_TARGET_KINDS = frozenset({
    "project_library", "project", "timeline", "track", "clip",
    "fusion_composition", "media", "marker", "runtime_setting",
})
_PRIVATE_IMPACT_TARGET_KIND_MAP = {
    "project_folder": "project",
    "media_pool_target": "media",
}


def _public_impact_target(target: Mapping[str, Any]) -> dict[str, Any]:
    private_kind = target.get("kind")
    public_kind = _PRIVATE_IMPACT_TARGET_KIND_MAP.get(private_kind, private_kind)
    stable_id = target.get("stableId")
    revision = target.get("revision")
    if (
        public_kind not in _PUBLIC_IMPACT_TARGET_KINDS
        or not isinstance(stable_id, str)
        or not isinstance(revision, str)
    ):
        raise ValidationError("Prepared action impact target is not publicly representable.")
    result = {"kind": public_kind, "stableId": stable_id, "revision": revision}
    for key in ("trackType", "trackIndex", "mediaRole"):
        if key in target:
            result[key] = target[key]
    return result


def _public_impact_targets(target: Mapping[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = target if isinstance(target, list) else [target]
    projected = [_public_impact_target(item) for item in targets if item.get("kind") != "artifact"]
    if not projected:
        raise ValidationError("Prepared action impact has no publicly representable mutation target.")
    return projected


def _specific_impact(context: Mapping[str, Any], action_id: str, value: Mapping[str, Any], target: Mapping[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    impact = _impact(context, action_id, value)
    impact["effects"][0]["targets"] = _public_impact_targets(target)
    return impact


def _project_result(
    action_id: str,
    *,
    target: Mapping[str, Any],
    data: Mapping[str, Any],
    evidence: tuple[str, ...],
    retry: str = "safe",
    changed: bool = True,
    recovery_extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    recovery = {
        "state": "not_needed",
        "retry": retry,
        "guidance": "No recovery is required for this verified result.",
        **dict(recovery_extra or {}),
    }
    return _assert_public({
        "actionId": action_id,
        "payload": {
            "status": "completed",
            "changed": changed,
            "target": dict(target),
            "data": dict(data),
            "verification": {
                "outcome": "passed",
                "evidence": [{"kind": kind, "summary": f"Validated by {kind.replace('_', ' ')}."} for kind in evidence],
                "protectedState": "preserved",
            },
            "recovery": recovery,
        },
    })


_SCRATCH_PREFIXES = (
    "CA CLI Color Proof", "CA Color Slice", "CA Color Warper", "CA Local Color",
    "CA ResolveFX", "CA Sky Isolation", "CutAgent Color Proof",
    "CutAgent ResolveFX", "CutAgent Scratch",
)


@dataclass(frozen=True)
class ProjectCleanupScratchDescriptor:
    action_id = "cutagent.action.project.cleanup_scratch"
    operation_class = "mutation"
    version = 1
    capability_id = _CAPABILITY_IDS[action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping) or not set(value) <= {"prefixes", "limit", "includeCurrent"}:
            raise ValidationError("Scratch cleanup input has an invalid shape.")
        prefixes = value.get("prefixes", list(_SCRATCH_PREFIXES))
        if not isinstance(prefixes, list) or not 1 <= len(prefixes) <= 64:
            raise ValidationError("Scratch cleanup requires between one and 64 prefixes.")
        normalized = []
        for prefix in prefixes:
            if not isinstance(prefix, str) or not prefix.strip() or len(prefix.strip()) > 256:
                raise ValidationError("Scratch cleanup prefixes must be bounded non-empty text.")
            normalized.append(prefix.strip())
        if len(set(normalized)) != len(normalized):
            raise ValidationError("Scratch cleanup prefixes must be unique.")
        if not set(normalized) <= set(_SCRATCH_PREFIXES):
            raise ValidationError("Scratch cleanup accepts only the reviewed CutAgent scratch prefixes.")
        limit = value.get("limit", 32)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1024:
            raise ValidationError("Scratch cleanup limit must be between one and 1024.")
        include_current = value.get("includeCurrent", False)
        if not isinstance(include_current, bool):
            raise ValidationError("includeCurrent must be boolean.")
        if include_current:
            raise ValidationError("Scratch cleanup cannot delete the carrier's active protected project.")
        return {"prefixes": normalized, "limit": limit, "includeCurrent": False}

    @staticmethod
    def _snapshot(folder_hint: str | None = None) -> dict[str, Any]:
        conn = get_connection(require_project=True)
        getter = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
        projects = getter() if callable(getter) else None
        folder_getter = getattr(conn.project_manager, "GetCurrentFolder", None)
        folder = folder_getter() if callable(folder_getter) else None
        if not isinstance(folder, str) or not folder:
            folder = folder_hint
        if not isinstance(projects, list) or not isinstance(folder, str) or not folder:
            raise APICallFailed("DaVinci Resolve project-folder cleanup readback is unavailable.")
        return {
            "projects": sorted(str(item) for item in projects),
            "folder": folder,
            "protected": _project_protected_state(conn),
        }

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        custody = _project_manager_custody(context, self.action_id, value)
        before = self._snapshot(str(custody["currentFolder"]["path"]))
        current = before["protected"]["projectName"]
        candidates = [
            name for name in before["projects"]
            if name != current and any(name.startswith(prefix) for prefix in value["prefixes"])
        ]
        candidates.sort(key=lambda name: name.encode())
        if not candidates:
            raise ValidationError("Scratch cleanup found no matching non-current projects.")
        if len(candidates) > value["limit"]:
            raise ValidationError("Scratch cleanup matched more projects than its signed limit.")
        targets = custody["targets"]
        if [target["name"] for target in targets] != candidates:
            raise ValidationError("Scratch cleanup targets drifted from Project Manager custody.")
        impact = _impact(context, self.action_id, value)
        impact["effects"][0]["targets"] = _public_impact_targets(targets)
        return {
            "targets": targets, "preState": before, "impact": impact,
            "lowering": {"candidates": candidates, "input": dict(value)},
            "verification": {"minimumEvidence": ["readback", "structural"]},
            "recovery": {"strategy": "manual_recovery_for_irreversible_project_deletion"},
        }

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        custody = _project_manager_custody(context, self.action_id, prepared["lowering"]["input"])
        return {"targets": prepared["targets"], "preState": self._snapshot(str(custody["currentFolder"]["path"]))}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        del context
        conn = get_connection(require_project=True)
        deleter = getattr(conn.project_manager, "DeleteProject", None)
        if not callable(deleter):
            raise APICallFailed("DaVinci Resolve project deletion is unavailable.")
        deleted = []
        for name in prepared["lowering"]["candidates"]:
            if _current_project_name(conn) == name:
                raise APICallFailed(
                    "Scratch cleanup will not delete a project that became current during cleanup."
                )
            existed_before = name in set(_project_names_in_current_folder(conn))
            deleter(name)
            if not _wait_for_project_deleted(conn, name, existed_before=existed_before):
                raise APICallFailed("DaVinci Resolve failed during exact scratch cleanup.")
            deleted.append(name)
        return {"deleted": deleted}

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        del context
        after = self._snapshot(prepared["preState"]["folder"])
        expected = sorted(
            name for name in prepared["preState"]["projects"]
            if name not in prepared["lowering"]["candidates"]
        )
        passed = result.get("deleted") == prepared["lowering"]["candidates"]
        passed = passed and after["projects"] == expected
        passed = passed and after["folder"] == prepared["preState"]["folder"]
        passed = passed and after["protected"] == prepared["preState"]["protected"]
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, after), "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del context, prepared, failure
        return {"outcome": "manual_required", "attempted": True, "manualActionRequired": True}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context
        folder = prepared["preState"]["folder"]
        return _project_result(
            self.action_id,
            target={"name": folder, "path": f"Projects / {folder}"},
            data={"candidates": prepared["lowering"]["candidates"], "deleted": result["deleted"], "skipped": [], "failures": []},
            evidence=("structural_readback", "context_readback"),
            retry="manual_only",
        )

    def validate_public_result(self, value: Any) -> bool:
        try:
            return value["actionId"] == self.action_id and value["payload"]["data"]["deleted"] == value["payload"]["data"]["candidates"]
        except Exception:
            return False


@dataclass(frozen=True)
class ProjectLifecycleDescriptor:
    action_id: str
    normalize: Callable[[Any], Mapping[str, Any]]
    operation_class = "mutation"
    version = 1

    @property
    def capability_id(self) -> str:
        return _CAPABILITY_IDS[self.action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        return _canonical(self.normalize(value))

    def _lower(
        self, context: Mapping[str, Any], value: Mapping[str, Any]
    ) -> dict[str, Any]:
        lowered = dict(value)
        artifact = _PROJECT_ARTIFACT_INPUTS.get(self.action_id)
        if artifact is not None:
            field, existing, directory = artifact
            lowered["path"] = _managed_artifact_path(
                context, value[field], existing=existing, directory=directory,
            )
            if self.action_id == "cutagent.action.project.library.backup":
                lowered["path"] = str(Path(lowered["path"]) / "backup")
            if (
                self.action_id == "cutagent.action.project.export"
                and Path(lowered["path"]).suffix.lower() != ".drp"
            ):
                raise ValidationError(
                    "Carrier-managed project export reservation must name the exact .drp destination."
                )
        if self.action_id in {
            "cutagent.action.project.library.create",
            "cutagent.action.project.library.restore",
        }:
            destination = _project_library_destination(context, value)
            lowered["directoryPath"] = destination["canonicalFinalPath"]
        return lowered

    def _snapshot(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        conn = get_connection(require_project=False)
        state: dict[str, Any] = {"database": _database(conn), "protected": _project_protected_state(conn) if conn.project else None}
        if self.action_id in {
            "cutagent.action.project.import",
            "cutagent.action.project.restore",
            "cutagent.action.project.delete",
        }:
            getter = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
            projects = getter() if callable(getter) else None
            if not isinstance(projects, list):
                raise APICallFailed("DaVinci Resolve project-list readback is unavailable.")
            state["projects"] = sorted(str(item) for item in projects)
        path = value.get("path")
        if isinstance(path, str) and Path(path).exists():
            stat = Path(path).stat()
            state["sourceIdentity"] = {
                "device": str(stat.st_dev),
                "inode": str(stat.st_ino),
                "size": stat.st_size,
                "mtimeNs": str(stat.st_mtime_ns),
                "sha256": _artifact_content_digest(Path(path)),
            }
        return state

    def _target(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        name = value.get("libraryName")
        if isinstance(name, str):
            return _library_target(context, name)
        if self.action_id in {"cutagent.action.project.import", "cutagent.action.project.restore"}:
            project, _ = _project_binding(context)
            return _library_target(context, project["projectLibraryId"])
        return _project_target(context, str(value.get("name") or value.get("projectName") or value.get("path")))

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        lowered = self._lower(context, value)
        custody = (
            _project_manager_custody(context, self.action_id, value)
            if self.action_id in _PROJECT_MANAGER_CUSTODY_ACTION_IDS
            else _project_library_custody(context, self.action_id, value)
            if self.action_id in _PROJECT_LIBRARY_CUSTODY_ACTION_IDS
            else None
        )
        if self.action_id in _PROJECT_LIBRARY_CUSTODY_ACTION_IDS:
            target = custody["target"]
        else:
            target = custody["targets"][0] if custody is not None else self._target(context, value)
        artifact = _PROJECT_ARTIFACT_INPUTS.get(self.action_id)
        targets = (
            _signed_artifact_targets(context, target, value[artifact[0]])
            if artifact is not None
            else [_signed_primary_target(context, target)]
        )
        if custody is not None and (targets[0]["stableId"] != target["stableId"] or targets[0]["revision"] != target["revision"]):
            raise ValidationError("Project target drifted from Project Manager custody.")
        if (
            self.action_id == "cutagent.action.project.open"
            and lowered.get("semantic") is True
            and lowered.get("projectId") != targets[0]["stableId"]
        ):
            raise ValidationError(
                "Project-open input identity drifted from Project Manager custody."
            )
        snapshot = self._snapshot(context, lowered)
        if self.action_id == "cutagent.action.project.delete":
            if value["name"] not in snapshot["projects"]:
                raise ValidationError("The project selected for deletion does not exist in the current folder.")
            protected = snapshot.get("protected") or {}
            if protected.get("projectName") == value["name"]:
                raise ValidationError(
                    "Deleting the active project would destroy the prepared action's protected context."
                )
        return {
            "targets": targets,
            "preState": snapshot,
            "impact": _specific_impact(context, self.action_id, value, targets),
            "lowering": {"input": lowered},
            "verification": {"minimumEvidence": ["readback", "structural"]},
            "recovery": {"strategy": "restore_prior_context_or_require_manual_recovery"},
        }

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        if self.action_id in _PROJECT_MANAGER_CUSTODY_ACTION_IDS:
            _project_manager_custody(context, self.action_id, prepared["lowering"]["input"])
        elif self.action_id in _PROJECT_LIBRARY_CUSTODY_ACTION_IDS:
            _project_library_custody(context, self.action_id, prepared["lowering"]["input"])
        return {"targets": prepared["targets"], "preState": self._snapshot(context, prepared["lowering"]["input"])}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        value = prepared["lowering"]["input"]
        conn = get_connection(require_project=False)
        action = self.action_id
        if action == "cutagent.action.project.export":
            path = value["path"]
            if conn.project_manager.ExportProject(value["name"], path, value.get("withStills", True)) is False:
                raise APICallFailed("DaVinci Resolve rejected the project export.")
            return {"path": path, "artifact": _artifact(path)}
        if action == "cutagent.action.project.library.backup":
            result = project_library_ops.backup_library(conn, name=value["libraryName"], path=value["path"])
            return {**result, "artifact": _artifact(value["path"], directory=True)}
        if action == "cutagent.action.project.library.create":
            destination = _project_library_destination(context, value)
            parent_identity = destination["parentIdentity"]
            return project_library_ops.create_library(
                conn, name=value["libraryName"], dir_path=value["directoryPath"],
                expected_parent_identity=(int(parent_identity["device"]), int(parent_identity["inode"])),
            )
        if action == "cutagent.action.project.library.restore":
            destination = _project_library_destination(context, value)
            parent_identity = destination["parentIdentity"]
            return project_library_ops.restore_library(
                conn, path=value["path"], name=value["libraryName"], dir_path=value["directoryPath"],
                expected_parent_identity=(int(parent_identity["device"]), int(parent_identity["inode"])),
            )
        if action == "cutagent.action.project.library.switch":
            target = prepared["targets"][0].get("database")
            if not isinstance(target, Mapping):
                raise ValidationError("Prepared project-library switch lost its exact native target.")
            return project_library_ops.switch_library(conn, target=dict(target))
        if action == "cutagent.action.project.open":
            before = _current_project_name(conn)
            if before == value["name"]:
                return {
                    "alreadyOpen": True, "name": before,
                    "nativeProjectId": _native_token(conn.project),
                    "nativeTimelineId": _native_token(getattr(conn, "timeline", None)),
                }
            opened = conn.project_manager.LoadProject(value["name"])
            if not opened:
                raise APICallFailed("DaVinci Resolve could not open the requested project.")
            conn.project = opened
            _refresh(conn)
            return {
                "alreadyOpen": False, "name": _current_project_name(conn),
                "nativeProjectId": _native_token(conn.project),
                "nativeTimelineId": _native_token(getattr(conn, "timeline", None)),
            }
        if action == "cutagent.action.project.restore":
            if conn.project_manager.RestoreProject(value["path"], value["name"]) is False:
                raise APICallFailed("DaVinci Resolve could not restore the project artifact.")
            _refresh(conn)
            getter = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
            after = sorted(str(item) for item in (getter() or [])) if callable(getter) else []
            added = sorted(set(after) - set(prepared["preState"]["projects"]))
            if added != [value["name"]]:
                raise APICallFailed("Project restore did not produce one exact project-list delta.")
            native_project_id = project_library_ops.current_project_folder_project_identity(conn, value["name"])
            if not native_project_id:
                raise APICallFailed("Project restore did not expose the exact restored Disk project identity.")
            protected = prepared["preState"].get("protected")
            protected_name = protected.get("projectName") if isinstance(protected, Mapping) else None
            if protected_name:
                current_name = conn.project.GetName() if conn.project else None
                if current_name != protected_name:
                    previous = conn.project_manager.LoadProject(protected_name)
                    if not previous:
                        raise APICallFailed("Project restore could not re-establish the protected project context.")
                    conn.project = previous
                    _refresh(conn)
            return {
                "restored": True,
                "name": value["name"],
                "nativeProjectId": native_project_id,
                "projects": after,
                "protected": _project_protected_state(conn) if conn.project else None,
            }
        if action == "cutagent.action.project.import":
            if conn.project_manager.ImportProject(value["path"], value["name"]) is False:
                raise APICallFailed("DaVinci Resolve could not import the project artifact.")
            _refresh(conn)
            getter = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
            after = sorted(str(item) for item in (getter() or [])) if callable(getter) else []
            added = sorted(set(after) - set(prepared["preState"]["projects"]))
            if added != [value["name"]]:
                raise APICallFailed("Project import did not produce one exact project-list delta.")
            native_project_id = project_library_ops.current_project_folder_project_identity(conn, value["name"])
            if not native_project_id:
                raise APICallFailed("Project import did not expose the exact imported Disk project identity.")
            return {"imported": True, "name": value["name"], "nativeProjectId": native_project_id, "projects": after}
        if action == "cutagent.action.project.delete":
            deleter = getattr(conn.project_manager, "DeleteProject", None)
            if not callable(deleter) or deleter(value["name"]) is False:
                raise APICallFailed("DaVinci Resolve could not delete the requested project.")
            getter = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
            projects = getter() if callable(getter) else None
            if not isinstance(projects, list):
                raise APICallFailed("Project-list readback became unavailable after deletion.")
            names = sorted(str(item) for item in projects)
            return {"deleted": value["name"] not in names, "projects": names}
        raise AssertionError(action)

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        value = prepared["lowering"]["input"]
        conn = get_connection(require_project=False)
        action = self.action_id
        if action in {"cutagent.action.project.export", "cutagent.action.project.library.backup"}:
            passed = bool(result.get("artifact"))
        elif action in {"cutagent.action.project.library.create", "cutagent.action.project.library.restore"}:
            destination = context.get("privateBindings", {}).get("projectLibraryDestination", {})
            final_path = Path(str(destination.get("canonicalFinalPath", "")))
            inventory = project_library_ops.project_library_inventory_identity(conn)
            matches = [database for database in inventory["databases"] if database.get("DbType") == "Disk" and database.get("DbName") == value["libraryName"]]
            passed = (
                result.get("changed") is True and result.get("verification") is not None
                and len(matches) == 1 and final_path.is_dir() and not final_path.is_symlink()
                and final_path.resolve() == final_path
            )
        elif action == "cutagent.action.project.library.switch":
            passed = result["current"].get("DbName") == value["libraryName"] and result["current"].get("DbType") == "Disk"
        elif action == "cutagent.action.project.open":
            active_timeline = getattr(conn, "timeline", None)
            native_timeline_id = _native_token(active_timeline)
            passed = (
                result.get("name") == value["name"]
                and result.get("nativeProjectId") == prepared["targets"][0].get("nativeId")
                and (
                    result.get("nativeTimelineId") is None
                    if active_timeline is None
                    else bool(native_timeline_id)
                    and result.get("nativeTimelineId") == native_timeline_id
                )
            )
        elif action == "cutagent.action.project.import":
            passed = result.get("imported") is True and result.get("name") == value["name"] and bool(result.get("nativeProjectId")) and result.get("projects") == sorted(
                [*prepared["preState"]["projects"], value["name"]]
            )
        elif action == "cutagent.action.project.delete":
            expected = sorted(
                name for name in prepared["preState"]["projects"] if name != value["name"]
            )
            passed = result.get("deleted") is True and result.get("projects") == expected
            passed = passed and _project_protected_state(conn) == prepared["preState"]["protected"]
        else:
            passed = result.get("restored") is True and result.get("name") == value["name"] and bool(result.get("nativeProjectId")) and result.get("projects") == sorted(
                [*prepared["preState"]["projects"], value["name"]]
            )
            passed = passed and result.get("protected") == prepared["preState"].get("protected")
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(action, result), "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del context, failure
        action = self.action_id
        attempted = True
        restored = False
        try:
            conn = get_connection(require_project=False)
            if action == "cutagent.action.project.library.switch":
                attempted = True
                before = prepared["preState"]
                restored = conn.project_manager.SetCurrentDatabase(before["database"]) is not False
                _refresh(conn)
                restored = restored and _database(conn) == before["database"]
            elif action in {"cutagent.action.project.export", "cutagent.action.project.library.backup"}:
                attempted = True
                # Caller-visible artifacts are preserved after uncertainty; deleting them is not race-safe.
                restored = False
            elif action == "cutagent.action.project.import":
                # The recovery callback intentionally receives no untrusted execution result;
                # without the exact imported name it must preserve state for manual review.
                restored = False
        except Exception:
            restored = False
        return {"outcome": "succeeded" if restored else "manual_required", "attempted": attempted, "manualActionRequired": not restored}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        value = prepared["lowering"]["input"]
        action = self.action_id
        conn = get_connection(require_project=False)
        if value.get("semantic") is True:
            signed_project, _ = _project_binding(context)
            semantic_project_id = None
            if ".library." in action or action == "cutagent.action.project.restore":
                semantic_project_id = signed_project["projectId"]
            elif action == "cutagent.action.project.open":
                semantic_project_id = prepared["targets"][0]["stableId"]
            semantic_context = _semantic_context(
                conn,
                context,
                project_id=semantic_project_id,
                timeline_native_id=(
                    result.get("nativeTimelineId")
                    if action == "cutagent.action.project.open"
                    else _UNSET_NATIVE_ID
                ),
            )
            if action == "cutagent.action.project.export":
                return _assert_public({
                    "project": {"id": value["projectId"], "name": value["name"]},
                    "artifact": {"kind": "project", "artifactId": value["destinationArtifactId"]},
                    "projectRevision": {"status": "available", "revision": value["precondition"]},
                })
            if action == "cutagent.action.project.library.backup":
                return _assert_public({
                    "library": {"name": value["libraryName"], "kind": "disk"},
                    "artifact": {"kind": "library_backup", "artifactId": value["destinationArtifactId"]},
                    "context": semantic_context,
                })
            if action in {
                "cutagent.action.project.library.create",
                "cutagent.action.project.library.restore",
                "cutagent.action.project.library.switch",
            }:
                return _assert_public({
                    "changed": True,
                    "library": {"name": value["libraryName"], "kind": "disk"},
                    "context": semantic_context,
                })
            if action == "cutagent.action.project.restore":
                return _assert_public({
                    "changed": True,
                    "restoredProject": {
                        "id": prepared["targets"][0]["stableId"],
                        "name": result["name"],
                    },
                    "context": semantic_context,
                })
            return _assert_public({
                "changed": not bool(result.get("alreadyOpen")),
                "context": semantic_context,
            })
        if action == "cutagent.action.project.export":
            return _project_result(
                action,
                target={"id": prepared["targets"][0]["stableId"], "name": value["name"]},
                data={"artifact": {"artifactId": value["destinationArtifactId"], "kind": "project"}},
                evidence=("artifact_readback",),
                retry="same_idempotency_key_required",
            )
        if action == "cutagent.action.project.library.backup":
            extra = {key: {"state": "not_needed", "guidance": "No recovery is needed after verified completion."} for key in ("artifactDestination", "activeContext")}
            return _project_result(action, target={"name": value["libraryName"], "kind": "disk"}, data={"artifact": {"artifactId": value["destinationArtifactId"], "kind": "library_backup"}, "activeContext": _active_context(conn, context)}, evidence=("artifact_readback", "context_readback"), retry="same_idempotency_key_required", recovery_extra=extra)
        if action in {"cutagent.action.project.library.create", "cutagent.action.project.library.restore"}:
            key = "created" if action.endswith("create") else "restored"
            extra = {name: {"state": "not_needed", "guidance": "No recovery is needed after verified completion."} for name in ("libraryRegistration", "activeContext")}
            return _project_result(action, target={"name": value["libraryName"], "kind": "disk"}, data={key: True, "activeContext": _active_context(conn, context)}, evidence=("structural_readback", "context_readback"), retry="same_idempotency_key_required", recovery_extra=extra)
        if action == "cutagent.action.project.library.switch":
            previous = result["previous"]
            previous_public = {"name": previous["DbName"], "kind": "disk"} if previous else None
            return _project_result(action, target={"name": value["libraryName"], "kind": "disk"}, data={"previousLibrary": previous_public}, evidence=("context_readback",))
        if action == "cutagent.action.project.open":
            return _project_result(
                action,
                target={"id": prepared["targets"][0]["stableId"], "name": value["name"]},
                data={"alreadyOpen": result["alreadyOpen"]},
                evidence=("context_readback",),
            )
        if action == "cutagent.action.project.import":
            return _project_result(
                action,
                target={"id": prepared["targets"][0]["stableId"], "name": result["name"]},
                data={"imported": True},
                evidence=("structural_readback",),
                retry="same_idempotency_key_required",
            )
        if action == "cutagent.action.project.delete":
            return _project_result(
                action,
                target={"id": prepared["targets"][0]["stableId"], "name": value["name"]},
                data={"deleted": True},
                evidence=("structural_readback", "context_readback"),
                retry="manual_only",
            )
        name = result["name"]
        target = {"id": prepared["targets"][0]["stableId"], "name": name}
        return _project_result(
            action,
            target=target,
            data={"restored": True},
            evidence=("structural_readback",),
            retry="same_idempotency_key_required",
        )

    def validate_public_result(self, value: Any) -> bool:
        try:
            if "actionId" not in value:
                if self.action_id == "cutagent.action.project.export":
                    return set(value) == {"project", "artifact", "projectRevision"}
                if self.action_id == "cutagent.action.project.library.backup":
                    return set(value) == {"library", "artifact", "context"}
                if ".library." in self.action_id:
                    return set(value) == {"changed", "library", "context"}
                if self.action_id == "cutagent.action.project.restore":
                    return set(value) == {"changed", "restoredProject", "context"}
                return set(value) == {"changed", "context"}
            return set(value) == {"actionId", "payload"} and value["actionId"] == self.action_id and value["payload"]["status"] == "completed" and value["payload"]["verification"]["outcome"] == "passed"
        except Exception:
            return False


def _validate_action_result(action_id: str, value: Any) -> bool:
    try:
        from ..sdk_action_descriptors.residual_av_prepared_action import (
            _schema as public_action_schema,
            _validate_schema as validate_public_action_schema,
        )
        validate_public_action_schema(value, public_action_schema(action_id, "result"))
        return True
    except Exception:
        return False


@dataclass(frozen=True)
class ProjectArchiveDescriptor:
    action_id = "cutagent.action.project.archive"
    operation_class = "mutation"
    version = 1
    capability_id = _CAPABILITY_IDS[action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        return _text_object(value, ("name", "destinationArtifactId"))

    def _snapshot(self) -> dict[str, Any]:
        conn = get_connection(require_project=False)
        return {"database": _database(conn), "projects": sorted(_project_names_in_current_folder(conn)), "active": _current_project_name(conn)}

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        custody = _project_manager_custody(context, self.action_id, value)
        before = self._snapshot()
        if value["name"] not in before["projects"] and value["name"] != before["active"]:
            raise ValidationError("The project selected for archive is absent from the current folder.")
        target = custody["targets"][0]
        reservation = _managed_artifact_path(context, value["destinationArtifactId"], existing=False, directory=True)
        lowered = {**value, "path": str(Path(reservation) / "archive")}
        targets = _signed_artifact_targets(
            context, target, value["destinationArtifactId"]
        )
        return {"targets": targets, "preState": before, "impact": _specific_impact(context, self.action_id, value, targets), "lowering": {"input": lowered}, "verification": {"minimumEvidence": ["artifact_readback", "context_readback"]}, "recovery": {"strategy": "preserve_archive_for_manual_review_on_uncertainty"}}

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        _project_manager_custody(context, self.action_id, prepared["lowering"]["input"])
        return {"targets": prepared["targets"], "preState": self._snapshot()}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        del context
        conn = get_connection(require_project=False)
        value = prepared["lowering"]["input"]
        if conn.project_manager.ArchiveProject(value["name"], value["path"]) is False:
            raise APICallFailed("DaVinci Resolve rejected the exact project archive request.")
        candidates = [Path(value["path"]), Path(f"{value['path']}.dra")]
        artifact = next((item for item in candidates if item.exists() and item.is_dir() and not item.is_symlink()), None)
        if artifact is None:
            raise APICallFailed("DaVinci Resolve reported archive success without the expected .dra artifact.")
        return {"path": str(artifact), "digest": _artifact_content_digest(artifact)}

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        del context
        after = self._snapshot()
        artifact = Path(result["path"])
        passed = artifact.is_dir() and not artifact.is_symlink() and _artifact_content_digest(artifact) == result["digest"] and after == prepared["preState"]
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, {"artifact": result, "context": after}), "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del context, prepared, failure
        return {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context
        value = prepared["lowering"]["input"]
        return _project_result(self.action_id, target={"id": prepared["targets"][0]["stableId"], "name": value["name"]}, data={"artifact": {"artifactId": value["destinationArtifactId"], "kind": "archive"}}, evidence=("artifact_readback", "context_readback"), retry="same_idempotency_key_required")

    def validate_public_result(self, value: Any) -> bool:
        return _validate_action_result(self.action_id, value)


@dataclass(frozen=True)
class ProjectCloseDescriptor:
    action_id = "cutagent.action.project.close"
    operation_class = "mutation"
    version = 1
    capability_id = _CAPABILITY_IDS[action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping) or value:
            raise ValidationError("Project close input must be an empty object.")
        return {}

    def _snapshot(self, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        conn = get_connection(require_project=False)
        snapshot = {"database": _database(conn), "active": _current_project_name(conn)}
        if context is not None and snapshot["active"] is not None:
            snapshot["binding"] = _assert_native_project_binding(context, conn)
        return snapshot

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        before = self._snapshot(context)
        if before["active"] is None:
            raise ValidationError("Project close requires an active project.")
        target = _signed_primary_target(context, _target(context))
        return {"targets": [target], "preState": before, "impact": _specific_impact(context, self.action_id, value, target), "lowering": {"input": {}}, "verification": {"minimumEvidence": ["context_readback"]}, "recovery": {"strategy": "reopen_exact_prior_project"}}

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        return {"targets": prepared["targets"], "preState": self._snapshot(context)}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        conn = get_connection(require_project=True)
        _assert_native_project_binding(context, conn)
        closer = getattr(conn.project_manager, "CloseProject", None)
        if not callable(closer):
            raise APICallFailed("DaVinci Resolve could not close the exact active project.")
        close_current_project_with_runtime_health(
            conn,
            project_name=prepared["preState"]["active"],
            current_database=prepared["preState"]["database"],
            description=f"project '{prepared['preState']['active']}' to stop being current",
            close_project=closer,
        )
        refreshed = get_connection(require_project=False)
        _refresh(refreshed)
        snapshot = {"database": _database(refreshed), "active": _current_project_name(refreshed)}
        if snapshot["active"] is None:
            return snapshot
        # The shared lifecycle helper may accept either a switched project or
        # DaVinci Resolve's unsaved Project Manager placeholder. Only the
        # strictly unlisted, timeline-free placeholder is a canonical closed
        # context for this public action; preserve every real project so
        # verification fails and recovery reopens the bound project.
        if _is_unlisted_project_manager_placeholder(refreshed, snapshot["active"]):
            return {**snapshot, "active": None}
        return snapshot

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        del context
        passed = result["database"] == prepared["preState"]["database"] and result["active"] is None
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, result), "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        restored = False
        try:
            conn = get_connection(require_project=False)
            restored = bool(conn.project_manager.LoadProject(prepared["preState"]["active"]))
            _refresh(conn)
            restored = restored and self._snapshot(context) == prepared["preState"]
        except Exception:
            restored = False
        return {"outcome": "succeeded" if restored else "manual_required", "attempted": True, "manualActionRequired": not restored}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context, result
        return _project_result(self.action_id, target={"id": prepared["targets"][0]["stableId"], "name": prepared["preState"]["active"]}, data={}, evidence=("context_readback",), retry="safe")

    def validate_public_result(self, value: Any) -> bool:
        return _validate_action_result(self.action_id, value)


def _project_folder_snapshot(conn: Any) -> dict[str, Any]:
    current = conn.project_manager.GetCurrentFolder()
    folders = conn.project_manager.GetFolderListInCurrentFolder()
    projects = conn.project_manager.GetProjectListInCurrentFolder()
    if not isinstance(current, str) or not current or not isinstance(folders, list) or not isinstance(projects, list):
        raise APICallFailed("DaVinci Resolve project-folder readback is unavailable.")
    return {"database": _database(conn), "current": current, "folders": sorted(map(str, folders)), "projects": sorted(map(str, projects))}


@dataclass(frozen=True)
class ProjectFolderDescriptor:
    action_id: str
    operation_class = "mutation"
    version = 1

    @property
    def capability_id(self) -> str:
        return _CAPABILITY_IDS[self.action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        required = ("name",) if self.action_id.endswith(("create", "delete", "open")) else ()
        return _text_object(value, required)

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        conn = get_connection(require_project=False)
        custody = _project_manager_custody(context, self.action_id, value)
        before = _project_folder_snapshot(conn)
        project, _ = _project_binding(context)
        name = value.get("name", project["projectLibraryId"])
        if self.action_id.endswith("create") and name in before["folders"]:
            raise ValidationError("The exact project folder already exists.")
        if self.action_id.endswith(("delete", "open")) and name not in before["folders"]:
            raise ValidationError("The exact project folder does not exist in the current folder.")
        target = _signed_primary_target(context, custody["targets"][0])
        return {"targets": [target], "preState": before, "impact": _specific_impact(context, self.action_id, value, target), "lowering": {"input": dict(value)}, "verification": {"minimumEvidence": ["context_readback", "structural_readback"]}, "recovery": {"strategy": "reverse_navigation_or_empty_folder_creation"}}

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        _project_manager_custody(context, self.action_id, prepared["lowering"]["input"])
        return {"targets": prepared["targets"], "preState": _project_folder_snapshot(get_connection(require_project=False))}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        del context
        conn = get_connection(require_project=False)
        value = prepared["lowering"]["input"]
        action = self.action_id.rsplit(".", 1)[-1]
        method = {"create": "CreateFolder", "delete": "DeleteFolder", "open": "OpenFolder", "up": "GotoParentFolder", "root": "GotoRootFolder"}[action]
        fn = getattr(conn.project_manager, method, None)
        if not callable(fn):
            if action == "root":
                from ..core import project_ops
                project_ops.goto_project_folder_root(conn)
            else:
                raise APICallFailed(f"DaVinci Resolve project-folder {action} is unavailable.")
        elif fn(*([value["name"]] if "name" in value else [])) is False and action not in {"up", "root"}:
            raise APICallFailed(f"DaVinci Resolve rejected project-folder {action}.")
        _refresh(conn)
        return _project_folder_snapshot(conn)

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        del context
        before = prepared["preState"]
        value = prepared["lowering"]["input"]
        action = self.action_id.rsplit(".", 1)[-1]
        if action == "create":
            passed = value["name"] in result["folders"] and result["projects"] == before["projects"] and result["current"] == before["current"]
        elif action == "delete":
            passed = value["name"] not in result["folders"] and result["projects"] == before["projects"] and result["current"] == before["current"]
        elif action == "open":
            passed = result["current"] == value["name"]
        elif action == "root":
            passed = result["current"].lower() in {"root", "project libraries", "projects"}
        else:
            passed = result["current"] != before["current"] or result == before
        passed = passed and result["database"] == before["database"]
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, result), "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del context, prepared, failure
        return {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context
        action = self.action_id.rsplit(".", 1)[-1]
        value = prepared["lowering"]["input"]
        name = value.get("name", result["current"])
        target = {"name": name, "path": name}
        data = ({"created": True} if action == "create" else {"deleted": True} if action == "delete" else {"previousPath": prepared["preState"]["current"], "currentPath": result["current"]} if action == "open" else {"currentPath": result["current"], "moved": result["current"] != prepared["preState"]["current"]} if action == "up" else {"currentPath": result["current"]})
        return _project_result(self.action_id, target=target, data=data, evidence=("structural_readback", "context_readback"))

    def validate_public_result(self, value: Any) -> bool:
        return _validate_action_result(self.action_id, value)


def _required_call(target: Any, method_name: str, *args: Any) -> Any:
    method = getattr(target, method_name, None)
    if not callable(method):
        raise APICallFailed(f"DaVinci Resolve does not expose {method_name} for project-content verification.")
    return method(*args)


def _project_content_fingerprint(conn: Any) -> dict[str, Any]:
    project = conn.project
    count = _required_call(project, "GetTimelineCount")
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 1_000:
        raise APICallFailed("DaVinci Resolve exposed an invalid timeline count for project-save verification.")
    timelines = []
    total_items = 0
    for timeline_index in range(1, count + 1):
        timeline = _required_call(project, "GetTimelineByIndex", timeline_index)
        if timeline is None:
            raise APICallFailed("DaVinci Resolve omitted a timeline during project-save verification.")
        name = str(_required_call(timeline, "GetName") or "")
        if not name:
            raise APICallFailed("DaVinci Resolve exposed an unnamed timeline during project-save verification.")
        timeline_id = _native_id(timeline, prefix="timeline_", fallback=f"{timeline_index}:{name}")
        markers = _required_call(timeline, "GetMarkers")
        settings = _required_call(timeline, "GetSetting")
        if not isinstance(markers, Mapping) or not isinstance(settings, Mapping):
            raise APICallFailed("DaVinci Resolve omitted timeline marker or settings content during project-save verification.")
        tracks: dict[str, Any] = {}
        for track_type in ("video", "audio", "subtitle"):
            track_count = _required_call(timeline, "GetTrackCount", track_type)
            if isinstance(track_count, bool) or not isinstance(track_count, int) or not 0 <= track_count <= 1_024:
                raise APICallFailed("DaVinci Resolve exposed an invalid track count during project-save verification.")
            track_rows = []
            for track_index in range(1, track_count + 1):
                items = _required_call(timeline, "GetItemListInTrack", track_type, track_index)
                if not isinstance(items, list):
                    raise APICallFailed("DaVinci Resolve omitted timeline items during project-save verification.")
                total_items += len(items)
                if total_items > 100_000:
                    raise APICallFailed("Project-save verification exceeds the bounded 100,000-item content inventory.")
                item_rows = []
                for ordinal, item in enumerate(items):
                    item_name = str(_required_call(item, "GetName") or "")
                    start = _required_call(item, "GetStart")
                    end = _required_call(item, "GetEnd")
                    duration = _required_call(item, "GetDuration")
                    if not item_name or any(isinstance(value, bool) or not isinstance(value, int) for value in (start, end, duration)):
                        raise APICallFailed("DaVinci Resolve exposed incomplete timeline-item content during project-save verification.")
                    media = _required_call(item, "GetMediaPoolItem")
                    media_id = None if media is None else _native_id(media, prefix="media_pool_item_", fallback=item_name)
                    item_rows.append({
                        "id": _native_id(item, prefix="timeline_item_", fallback=f"{timeline_id}:{track_type}:{track_index}:{ordinal}:{item_name}:{start}:{end}"),
                        "mediaId": media_id,
                        "name": item_name,
                        "start": start,
                        "end": end,
                        "duration": duration,
                    })
                track_rows.append({"index": track_index, "items": item_rows})
            tracks[track_type] = track_rows
        start = _required_call(timeline, "GetStartFrame")
        end = _required_call(timeline, "GetEndFrame")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (start, end)):
            raise APICallFailed("DaVinci Resolve exposed incomplete timeline bounds during project-save verification.")
        timelines.append({
            "id": timeline_id,
            "name": name,
            "start": start,
            "end": end,
            "markers": {str(key): _canonical(value) for key, value in sorted(markers.items(), key=lambda item: str(item[0]))},
            "settings": _canonical(settings),
            "tracks": tracks,
        })
    media = sdk_live_inspection.inspect_media_pool_page(
        conn, deadline_at_ms=int(time.time() * 1_000) + 60_000,
        offset=0, page_size=1, search=None,
    )
    if media.get("ambiguous_native_ids") is True or not isinstance(media.get("pool_digest"), str):
        raise APICallFailed("DaVinci Resolve Media Pool identity is ambiguous during project-save verification.")
    current_timeline = getattr(conn, "timeline", None)
    return {
        "timelinesDigest": _digest(timelines),
        "timelineCount": count,
        "currentTimelineId": None if current_timeline is None else _native_id(current_timeline, prefix="timeline_", fallback=str(_required_call(current_timeline, "GetName"))),
        "mediaPoolDigest": f"sha256:{media['pool_digest']}",
        "mediaPoolEntryCount": media["total"],
    }


def _preset_expected_settings(preset: Mapping[str, Any]) -> dict[str, Any]:
    record = preset.get("record")
    expected = record.get("Settings") if isinstance(record, Mapping) else None
    if isinstance(expected, Mapping) and expected:
        return _canonical(expected)
    if (
        isinstance(record, Mapping)
        and set(record) == {"Name", "Width", "Height"}
        and isinstance(record.get("Width"), int)
        and not isinstance(record.get("Width"), bool)
        and record["Width"] > 0
        and isinstance(record.get("Height"), int)
        and not isinstance(record.get("Height"), bool)
        and record["Height"] > 0
    ):
        return {
            "timelineResolutionWidth": str(record["Width"]),
            "timelineResolutionHeight": str(record["Height"]),
        }
    raise APICallFailed("The requested native project preset does not expose exact expected settings.")


def _preset_has_complete_settings(preset: Mapping[str, Any]) -> bool:
    record = preset.get("record")
    return isinstance(record, Mapping) and isinstance(record.get("Settings"), Mapping) and bool(record["Settings"])


def _stable_preset_inventory(presets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [preset for preset in presets if preset.get("name") != "Current Project"]


def _project_save_snapshot_matches(
    before: Mapping[str, Any], after: Mapping[str, Any],
) -> bool:
    expected_projects = list(before["projects"])
    first_persistence = before["active"] not in before["projects"]
    if first_persistence:
        expected_projects = sorted([*expected_projects, before["active"]])
    if after.get("projects") != expected_projects:
        return False

    before_settings = before.get("settings")
    after_settings = after.get("settings")
    if not isinstance(before_settings, Mapping) or not isinstance(after_settings, Mapping):
        return False
    if set(before_settings) != set(after_settings):
        return False
    changed_settings = {
        key for key in before_settings if before_settings[key] != after_settings[key]
    }
    if changed_settings and not (
        changed_settings == {"perfCacheClipsLocation"}
        and before_settings["perfCacheClipsLocation"] == ""
        and isinstance(after_settings["perfCacheClipsLocation"], str)
        and bool(after_settings["perfCacheClipsLocation"].strip())
    ):
        return False

    return {
        key: value for key, value in after.items()
        if key not in {"projects", "settings"}
    } == {
        key: value for key, value in before.items()
        if key not in {"projects", "settings"}
    }


@dataclass(frozen=True)
class ProjectContextDescriptor:
    action_id: str
    operation_class = "mutation"
    version = 1

    @property
    def capability_id(self) -> str:
        return _CAPABILITY_IDS[self.action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        required = {
            "cutagent.action.project.cloud.create": ("name",),
            "cutagent.action.project.cloud.import": ("sourceArtifactId", "name"),
            "cutagent.action.project.cloud.open": ("name",),
            "cutagent.action.project.cloud.restore": ("sourceArtifactId", "name"),
            "cutagent.action.project.preset.load": ("name",),
            "cutagent.action.project.preset.save": ("name",),
            "cutagent.action.project.save": (),
        }[self.action_id]
        optional = tuple({"collaboration", "mediaPath", "syncMode", "name"} - set(required)) if ".cloud." in self.action_id else ()
        if not isinstance(value, Mapping) or not set(value) <= set(required) | set(optional):
            raise ValidationError("Project context action input has an invalid shape.")
        data = dict(value)
        for key in required:
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ValidationError("Project context action input requires bounded non-empty text.")
            data[key] = data[key].strip()
        return data

    def _snapshot(self, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        verified_internal = self.action_id in _VERIFIED_PROJECT_INTERNAL_ACTIONS
        conn = get_connection(require_project=verified_internal)
        presets = []
        settings = None
        if conn.project is not None:
            preset_getter = getattr(conn.project, "GetPresetList", None)
            if verified_internal and not callable(preset_getter):
                raise APICallFailed("DaVinci Resolve did not expose an exact project-preset inventory.")
            raw_presets = preset_getter() if callable(preset_getter) else []
            if isinstance(raw_presets, list):
                if verified_internal:
                    for item in raw_presets:
                        if isinstance(item, Mapping):
                            record = _canonical(item)
                            name = record.get("Name")
                        elif isinstance(item, str):
                            record = item
                            name = item
                        else:
                            raise APICallFailed("DaVinci Resolve exposed a non-canonical project-preset record.")
                        if not isinstance(name, str) or not name:
                            raise APICallFailed("DaVinci Resolve exposed a project preset without an exact name.")
                        presets.append({"name": name, "record": record})
                    presets.sort(key=lambda item: (item["name"], _digest(item["record"])))
                    if len({item["name"] for item in presets}) != len(presets):
                        raise ValidationError("Project preset names are ambiguous in the native inventory.")
                else:
                    presets = sorted(str(item.get("Name", "") if isinstance(item, Mapping) else item) for item in raw_presets)
            elif verified_internal:
                raise APICallFailed("DaVinci Resolve did not expose an exact project-preset inventory.")
            settings_getter = getattr(conn.project, "GetSetting", None)
            raw_settings = settings_getter() if callable(settings_getter) else None
            if isinstance(raw_settings, Mapping):
                settings = _canonical(raw_settings)
            elif verified_internal:
                raise APICallFailed("DaVinci Resolve did not expose complete project settings for verification.")
        snapshot = {
            "database": _database(conn),
            "active": _current_project_name(conn),
            "projects": sorted(_project_names_in_current_folder(conn)),
            "presets": presets,
            "settings": settings,
        }
        if verified_internal:
            snapshot["protected"] = _project_protected_state(conn, context)
        if self.action_id == "cutagent.action.project.save":
            snapshot["content"] = _project_content_fingerprint(conn)
        return snapshot

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        before = self._snapshot(context if self.action_id in _VERIFIED_PROJECT_INTERNAL_ACTIONS else None)
        name = before["active"] if self.action_id in _VERIFIED_PROJECT_INTERNAL_ACTIONS else value.get("name") or before["active"]
        target = _project_target(context, str(name))
        if self.action_id.endswith("preset.save") and value["name"] in {item["name"] for item in before["presets"]}:
            raise ValidationError("Project preset save requires a new preset name for authoritative readback.")
        if self.action_id.endswith("preset.save"):
            conn = get_connection(require_project=True)
            if not callable(getattr(conn.project, "DeletePreset", None)):
                raise APICallFailed("DaVinci Resolve does not expose compensating project-preset deletion.")
            if not any(
                callable(getattr(conn.project, method_name, None))
                for method_name in ("SavePreset", "SaveAsPreset", "CreatePreset")
            ):
                raise APICallFailed("DaVinci Resolve does not expose project-preset save.")
        if self.action_id.endswith("preset.load") and value["name"] not in {item["name"] for item in before["presets"]}:
            raise ValidationError("Project preset load requires one exact existing preset record.")
        if self.action_id.endswith("preset.load"):
            preset = next(item for item in before["presets"] if item["name"] == value["name"])
            expected_settings = _preset_expected_settings(preset)
            if not set(expected_settings) <= set(before["settings"]):
                raise APICallFailed("The requested project preset does not expose a complete settings key set.")
            if _preset_has_complete_settings(preset) and set(expected_settings) != set(before["settings"]):
                raise APICallFailed("The requested project preset does not expose a complete settings key set.")
        lowered = dict(value)
        artifact = _CLOUD_ARTIFACT_INPUTS.get(self.action_id)
        if artifact is not None:
            field, directory = artifact
            lowered["folder" if directory else "filePath"] = _managed_artifact_path(
                context, value[field], existing=True, directory=directory,
            )
        targets = (
            _signed_artifact_targets(context, target, value[artifact[0]])
            if artifact is not None
            else [_signed_primary_target(context, target)]
        )
        recovery_strategy = {
            "cutagent.action.project.preset.load": "restore_exact_project_settings",
            "cutagent.action.project.preset.save": "delete_created_preset_and_verify_inventory",
            "cutagent.action.project.save": "preserve_active_project_and_verify_snapshot",
        }.get(self.action_id, "manual_recovery_if_effect_readback_fails")
        return {"targets": targets, "preState": before, "impact": _specific_impact(context, self.action_id, value, targets), "lowering": {"input": lowered}, "verification": {"minimumEvidence": ["structural_readback", "context_readback"]}, "recovery": {"strategy": recovery_strategy}}

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        return {"targets": prepared["targets"], "preState": self._snapshot(context if self.action_id in _VERIFIED_PROJECT_INTERNAL_ACTIONS else None)}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        value = prepared["lowering"]["input"]
        conn = get_connection(require_project=self.action_id in {
            "cutagent.action.project.preset.load",
            "cutagent.action.project.preset.save",
            "cutagent.action.project.save",
        })
        if self.action_id in _VERIFIED_PROJECT_INTERNAL_ACTIONS:
            _assert_native_project_binding(context, conn)
        if self.action_id == "cutagent.action.project.cloud.create":
            return project_ops.create_cloud_project(conn, value["name"], value.get("mediaPath"), value.get("syncMode"), value.get("collaboration", False))
        if self.action_id == "cutagent.action.project.cloud.open":
            return project_ops.open_cloud_project(conn, value["name"], value.get("mediaPath"), value.get("syncMode"))
        if self.action_id == "cutagent.action.project.cloud.import":
            return project_ops.import_cloud_project(conn, value["filePath"], value.get("name"), value.get("mediaPath"))
        if self.action_id == "cutagent.action.project.cloud.restore":
            return project_ops.restore_cloud_project(conn, value["folder"], value.get("name"), value.get("mediaPath"))
        if self.action_id == "cutagent.action.project.preset.load":
            setter = getattr(conn.project, "SetPreset", None)
            restorer = getattr(conn.project, "SetSetting", None)
            preset = next((item for item in prepared["preState"]["presets"] if item["name"] == value["name"]), None)
            if preset is None or not callable(setter) or not callable(restorer):
                raise APICallFailed("DaVinci Resolve could not load the requested project preset.")
            expected_settings = _preset_expected_settings(preset)
            if _preset_has_complete_settings(preset) and expected_settings == prepared["preState"]["settings"]:
                return {"loaded": True, "changed": False, "expectedSettings": expected_settings}
            try:
                loaded = setter(preset["record"])
            except Exception:
                loaded = False
            if loaded is False and preset["record"] != preset["name"]:
                loaded = setter(preset["name"])
            if loaded is False:
                raise APICallFailed("DaVinci Resolve could not load the requested project preset.")
            current_settings = conn.project.GetSetting()
            if not isinstance(current_settings, Mapping):
                raise APICallFailed("DaVinci Resolve did not expose complete project settings after loading the preset.")
            return {
                "loaded": True,
                "changed": _canonical(current_settings) != prepared["preState"]["settings"],
                "expectedSettings": expected_settings,
            }
        if self.action_id == "cutagent.action.project.preset.save":
            if not callable(getattr(conn.project, "DeletePreset", None)):
                raise APICallFailed("DaVinci Resolve does not expose compensating project-preset deletion.")
            for method_name in ("SavePreset", "SaveAsPreset", "CreatePreset"):
                saver = getattr(conn.project, method_name, None)
                if callable(saver):
                    if saver(value["name"]) is False:
                        raise APICallFailed("DaVinci Resolve rejected the project-preset save.")
                    return {"saved": True, "method": method_name}
            raise APICallFailed("DaVinci Resolve does not expose project-preset save.")
        if not project_ops.save_current_project_if_available(conn):
            raise APICallFailed("DaVinci Resolve did not confirm the current project save.")
        _assert_native_project_binding(context, conn)
        # Preserve the working project. Persistence across reopen belongs to an
        # explicit acceptance scenario, not to every ordinary Save operation.
        return {"saved": True, "reopened": False}

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        after = self._snapshot(context if self.action_id in _VERIFIED_PROJECT_INTERNAL_ACTIONS else None)
        before = prepared["preState"]
        value = prepared["lowering"]["input"]
        context_preserved = after["database"] == before["database"]
        if self.action_id in _VERIFIED_PROJECT_INTERNAL_ACTIONS:
            expected_projects = before["projects"]
            if (
                self.action_id == "cutagent.action.project.save"
                and before["active"] not in before["projects"]
            ):
                expected_projects = sorted([*before["projects"], before["active"]])
            context_preserved = context_preserved and (
                after["active"] == before["active"]
                and after["projects"] == expected_projects
                and after["protected"] == before["protected"]
            )
        if self.action_id == "cutagent.action.project.preset.load":
            passed = (
                bool(result.get("loaded"))
                and _stable_preset_inventory(after["presets"])
                == _stable_preset_inventory(before["presets"])
                and all(
                    after["settings"].get(key) == expected
                    for key, expected in result.get("expectedSettings", {}).items()
                )
                and result.get("changed") == (after["settings"] != before["settings"])
            )
        elif self.action_id == "cutagent.action.project.preset.save":
            added = [item for item in after["presets"] if item not in before["presets"]]
            retained = [item for item in after["presets"] if item in before["presets"]]
            passed = bool(result.get("saved")) and retained == before["presets"] and len(added) == 1 and added[0]["name"] == value["name"] and after["settings"] == before["settings"]
        elif self.action_id == "cutagent.action.project.save":
            passed = (
                bool(result.get("saved"))
                and _project_save_snapshot_matches(before, after)
            )
        else:
            expected = value.get("name")
            added = sorted(set(after["projects"]) - set(before["projects"]))
            if self.action_id == "cutagent.action.project.cloud.open":
                passed = bool(result) and bool(expected) and after["active"] == expected
            elif expected:
                passed = bool(result) and after["active"] == expected and expected in after["projects"]
            else:
                passed = bool(result) and len(added) == 1 and after["active"] == added[0]
        passed = passed and context_preserved
        outcome = "passed" if passed else "failed"
        return {"outcome": outcome, "evidence": _evidence(self.action_id, {"result": result, "before": before, "after": after}), "protectedStatePreserved": context_preserved}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        if self.action_id not in _VERIFIED_PROJECT_INTERNAL_ACTIONS:
            return {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}
        attempted = False
        try:
            conn = get_connection(require_project=False)
            before = prepared["preState"]
            if _current_project_name(conn) != before["active"]:
                if self.action_id == "cutagent.action.project.save":
                    return {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}
                loader = getattr(conn.project_manager, "LoadProject", None)
                attempted = True
                if not callable(loader) or not loader(before["active"]):
                    return {"outcome": "manual_required", "attempted": True, "manualActionRequired": True}
                _refresh(conn)
            _assert_native_project_binding(context, conn)
            current = self._snapshot(context)
            if current == before or (
                self.action_id == "cutagent.action.project.save"
                and _project_save_snapshot_matches(before, current)
            ):
                return {"outcome": "succeeded", "attempted": attempted, "manualActionRequired": False}
            if self.action_id == "cutagent.action.project.preset.load":
                setter = getattr(conn.project, "SetSetting", None)
                if not callable(setter) or set(current["settings"]) != set(before["settings"]):
                    return {"outcome": "manual_required", "attempted": attempted, "manualActionRequired": True}
                attempted = True
                for key, old_value in before["settings"].items():
                    if current["settings"][key] == old_value:
                        continue
                    if setter(key, old_value) is False:
                        return {"outcome": "manual_required", "attempted": True, "manualActionRequired": True}
            elif self.action_id == "cutagent.action.project.preset.save":
                added = [item for item in current["presets"] if item not in before["presets"]]
                deleter = getattr(conn.project, "DeletePreset", None)
                if len(added) != 1 or added[0]["name"] != prepared["lowering"]["input"]["name"] or not callable(deleter):
                    return {"outcome": "manual_required", "attempted": attempted, "manualActionRequired": True}
                attempted = True
                try:
                    deleted = deleter(added[0]["record"])
                except Exception:
                    deleted = False
                if deleted is False and added[0]["record"] != added[0]["name"]:
                    deleted = deleter(added[0]["name"])
                if deleted is False:
                    return {"outcome": "manual_required", "attempted": True, "manualActionRequired": True}
            else:
                return {"outcome": "manual_required", "attempted": attempted, "manualActionRequired": True}
            restored = self._snapshot(context) == before
            return {"outcome": "succeeded" if restored else "manual_required", "attempted": attempted, "manualActionRequired": not restored}
        except Exception:
            return {"outcome": "manual_required", "attempted": attempted, "manualActionRequired": True}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context
        value = prepared["lowering"]["input"]
        fallback = value.get("filePath") or value.get("folder") or value.get("sourceArtifactId")
        name = value.get("name") or (Path(fallback).stem if isinstance(fallback, str) else prepared["preState"]["active"])
        target = {"name": str(name)}
        if ".cloud." in self.action_id or self.action_id == "cutagent.action.project.save":
            target["id"] = prepared["targets"][0]["stableId"]
        data = {"requiresCloudAccount": True, "manualStepRequired": True} if ".cloud." in self.action_id else {"loaded": True} if self.action_id.endswith("preset.load") else {"saved": True}
        if self.action_id in _VERIFIED_PROJECT_INTERNAL_ACTIONS:
            return _project_result(
                self.action_id,
                target=target,
                data=data,
                evidence=("structural_readback", "context_readback"),
                retry="safe" if self.action_id != "cutagent.action.project.preset.save" else "same_idempotency_key_required",
                changed=result.get("changed", True),
            )
        return _assert_public({"actionId": self.action_id, "payload": {"status": "manual_review_required", "changed": bool(result), "target": target, "data": data, "verification": {"outcome": "manual_review_required", "evidence": [{"kind": "manual_review", "summary": "The runtime call completed but DaVinci Resolve does not expose authoritative structural readback for this operation."}], "protectedState": "preserved" if ".cloud." not in self.action_id else "not_proven"}, "recovery": {"state": "manual_required", "retry": "manual_only", "guidance": "Verify the requested operation in DaVinci Resolve before continuing."}}})

    def validate_public_result(self, value: Any) -> bool:
        return _validate_action_result(self.action_id, value)


def _folder_rows(node: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [{"kind": "folder", "path": node["path"], "clipCount": node["clip_count"], "subfolderCount": node["subfolder_count"]}]
    for child in node["subfolders"]:
        rows.extend(_folder_rows(child))
    return rows


def _folder_snapshot(conn: Any) -> list[dict[str, Any]]:
    return _folder_rows(media_pool.serialize_folder_tree(media_pool.get_folder_tree(conn)))


def _canonical_folder_path(conn: Any, path: str) -> str:
    logical = "/".join(part for part in path.split("/") if part)
    root_name = conn.media_pool.GetRootFolder().GetName()
    if logical == root_name or logical.startswith(f"{root_name}/"):
        return logical
    return f"{root_name}/{logical}"


def _authoritative_media_revision(conn: Any, project_id: str) -> str:
    inspected = sdk_live_inspection.inspect_media_pool_page(
        conn,
        deadline_at_ms=int(time.time() * 1000) + 60_000,
        offset=0,
        page_size=1,
        search=None,
    )
    return _sdk_digest(
        "revision_",
        {"projectId": project_id, "poolDigest": inspected["pool_digest"]},
    )


def _mapping_read(target: Any, method_name: str, label: str) -> dict[str, Any]:
    getter = getattr(target, method_name, None)
    if not callable(getter):
        raise APICallFailed(f"DaVinci Resolve {label} protected-state readback is unavailable.")
    value = getter()
    if not isinstance(value, Mapping):
        raise APICallFailed(f"DaVinci Resolve returned malformed {label} protected-state readback.")
    return {str(key): item for key, item in value.items()}


def _media_state(conn: Any, project_id: str) -> dict[str, Any]:
    folders: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    for folder, path in _walk_media_folders(conn.media_pool.GetRootFolder()):
        native = _native_token(folder)
        if not native:
            raise ValidationError("Every mutable Media Pool folder requires a durable native identity.")
        folder_id = _sdk_native_id("media_pool_folder_", project_id, native)
        clips = folder.GetClipList() or []
        children = folder.GetSubFolderList() or []
        folders.append({
            "id": folder_id,
            "path": path,
            "clipCount": len(clips),
            "subfolderCount": len(children),
        })
        for clip in clips:
            clip_native = sdk_live_inspection.media_pool_native_id(clip)
            if not clip_native:
                raise ValidationError("Every protected Media Pool asset requires a durable native identity.")
            asset_id = _sdk_native_id("media_pool_item_", project_id, clip_native)
            def optional(method_name: str) -> Any:
                getter = getattr(clip, method_name, None)
                if not callable(getter):
                    return {"status": "unavailable"}
                try:
                    raw = getter()
                    if isinstance(raw, Mapping) and any(not isinstance(key, str) for key in raw):
                        normalized = {str(key): value for key, value in raw.items()}
                        if len(normalized) != len(raw):
                            raise ValidationError("DaVinci Resolve returned ambiguous Media Pool readback keys.")
                        raw = normalized
                    return _canonical(raw)
                except Exception:
                    return {"status": "unavailable"}

            def optional_pool(method_name: str) -> Any:
                getter = getattr(conn.media_pool, method_name, None)
                if not callable(getter):
                    return {"status": "unavailable"}
                try:
                    return _canonical(getter(clip) or [])
                except Exception:
                    return {"status": "unavailable"}

            assets.append({
                "id": asset_id,
                "folderId": folder_id,
                "folder": path,
                "name": clip.GetName(),
                "metadata": _mapping_read(clip, "GetMetadata", "clip metadata"),
                "properties": _mapping_read(clip, "GetClipProperty", "clip properties"),
                "thirdPartyMetadata": _mapping_read(
                    clip,
                    "GetThirdPartyMetadata",
                    "clip third-party metadata",
                ),
                "flags": optional("GetFlagList"),
                "markers": optional("GetMarkers"),
                "marks": optional("GetMarkInOut"),
                "audioMapping": optional("GetAudioMapping"),
                "mattes": optional_pool("GetClipMatteList"),
            })
    selected_getter = getattr(conn.media_pool, "GetSelectedClips", None)
    selected_ids = []
    if callable(selected_getter):
        for clip in selected_getter() or []:
            native = sdk_live_inspection.media_pool_native_id(clip)
            if native:
                selected_ids.append(_sdk_native_id("media_pool_item_", project_id, native))
    current_getter = getattr(conn.media_pool, "GetCurrentFolder", None)
    current_folder = current_getter() if callable(current_getter) else None
    current_native = _native_token(current_folder) if current_folder is not None else None
    timelines = []
    current_timeline_getter = getattr(conn.project, "GetCurrentTimeline", None)
    current_timeline = current_timeline_getter() if callable(current_timeline_getter) else None
    current_timeline_native = _native_token(current_timeline) if current_timeline is not None else None
    count_getter = getattr(conn.project, "GetTimelineCount", None)
    timeline_getter = getattr(conn.project, "GetTimelineByIndex", None)
    if callable(count_getter) and callable(timeline_getter):
        for index in range(1, int(count_getter() or 0) + 1):
            timeline = timeline_getter(index)
            native = _native_token(timeline) if timeline is not None else None
            name_getter = getattr(timeline, "GetName", None) if timeline is not None else None
            if native and callable(name_getter):
                timeline_sources = []
                track_count_getter = getattr(timeline, "GetTrackCount", None)
                track_items_getter = getattr(timeline, "GetItemListInTrack", None)
                if callable(track_count_getter) and callable(track_items_getter):
                    for kind_index, track_kind in enumerate(("video", "audio")):
                        for track_index in range(1, int(track_count_getter(track_kind) or 0) + 1):
                            for item_index, item in enumerate(track_items_getter(track_kind, track_index) or []):
                                media_getter = getattr(item, "GetMediaPoolItem", None)
                                media_item = media_getter() if callable(media_getter) else None
                                media_native = sdk_live_inspection.media_pool_native_id(media_item) if media_item is not None else None
                                if not media_native:
                                    continue
                                start_getter = getattr(item, "GetStart", None)
                                start = int(start_getter() or 0) if callable(start_getter) else item_index
                                timeline_sources.append((
                                    start, kind_index, track_index, item_index,
                                    _sdk_native_id("media_pool_item_", project_id, media_native),
                                ))
                timeline_assets = []
                seen_sources = set()
                for start, _kind, _track, _index, asset_id in sorted(timeline_sources):
                    source_key = (start, asset_id)
                    if source_key not in seen_sources:
                        timeline_assets.append(asset_id)
                        seen_sources.add(source_key)
                timelines.append({
                    "id": _sdk_native_id("timeline_", project_id, native),
                    "name": str(name_getter()),
                    "mediaPoolItemIds": timeline_assets,
                    # Usage counts each video/audio timeline item, while the ordered
                    # source list coalesces linked AV items at the same position.
                    "mediaPoolItemUsageCounts": dict(sorted(Counter(
                        row[4] for row in timeline_sources
                    ).items())),
                })
    return {
        "revision": _authoritative_media_revision(conn, project_id),
        "folders": sorted(folders, key=lambda row: row["id"]),
        "assets": sorted(assets, key=lambda row: row["id"]),
        "selectedIds": sorted(selected_ids),
        "currentFolderId": _sdk_native_id("media_pool_folder_", project_id, current_native) if current_native else None,
        "currentTimelineId": _sdk_native_id("timeline_", project_id, current_timeline_native) if current_timeline_native else None,
        "timelines": sorted(timelines, key=lambda row: row["id"]),
    }


def _without_casefold_key(values: Mapping[str, Any], key: str) -> dict[str, Any]:
    folded = key.casefold()
    return {name: value for name, value in values.items() if name.casefold() != folded}


def _casefold_value(values: Mapping[str, Any], key: str) -> Any:
    matches = [value for name, value in values.items() if name.casefold() == key.casefold()]
    if len(matches) > 1:
        raise ValidationError("DaVinci Resolve returned ambiguous case-insensitive Media Pool fields.")
    return matches[0] if matches else None


_SEMANTIC_METADATA_NATIVE_KEYS = {
    "description": "Description",
    "comments": "Comments",
    "keywords": "Keywords",
    "shot": "Shot",
    "scene": "Scene",
    "take": "Take",
    "angle": "Angle",
    "camera": "Camera #",
    "reel": "Reel Name",
    "dateRecorded": "Date Recorded",
    "goodTake": "Good Take",
    "clipColor": "Clip Color",
}


def _semantic_metadata_location(key: str) -> tuple[str, str]:
    native_key = _SEMANTIC_METADATA_NATIVE_KEYS[key]
    return ("properties", native_key) if key == "clipColor" else ("metadata", native_key)


def _protected_semantic_media_state(
    state: Mapping[str, Any], target_id: str, keys: tuple[str, ...]
) -> dict[str, Any]:
    protected = {"folders": [dict(row) for row in state["folders"]], "assets": []}
    allowed = {_semantic_metadata_location(key) for key in keys}
    for original in state["assets"]:
        row = deepcopy(original)
        if row["id"] == target_id:
            # DaVinci Resolve mirrors Comments into clip properties. Permit
            # that projection only when it agrees with the metadata readback.
            if "comments" in keys and (
                _casefold_value(row["properties"], "Comments")
                == (_casefold_value(row["metadata"], "Comments") or "")
            ):
                row["properties"] = _without_casefold_key(row["properties"], "Comments")
            for field_kind, native_key in allowed:
                row[field_kind] = _without_casefold_key(row[field_kind], native_key)
        protected["assets"].append(row)
    return protected


def _protected_media_state(
    state: Mapping[str, Any],
    *,
    target_id: str | None = None,
    field_kind: str | None = None,
    allowed_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    protected = {"folders": [dict(row) for row in state["folders"]], "assets": []}
    for original in state["assets"]:
        row = deepcopy(original)
        if row["id"] == target_id and field_kind:
            for key in allowed_keys:
                row[field_kind] = _without_casefold_key(row[field_kind], key)
                if field_kind == "properties" and key.casefold() == "clip name":
                    row.pop("name", None)
        protected["assets"].append(row)
    return protected


def _private_media_binding(context: Mapping[str, Any]) -> dict[str, Any]:
    bindings = context.get("privateBindings")
    media = bindings.get("mediaPool") if isinstance(bindings, Mapping) else None
    required = {"operation", "parentId", "targetId", "targetPath", "targetName", "revision"}
    if not isinstance(media, Mapping) or set(media) != required:
        raise ValidationError("Prepared Media Pool action requires carrier-owned private identity binding.")
    if media["operation"] not in {"create", "delete", "asset"} or not isinstance(media["revision"], str):
        raise ValidationError("Prepared Media Pool private identity binding is malformed.")
    return dict(media)


def _media_applicability() -> dict[str, Any]:
    declared = "declared_unverified"
    return {
        "overall": "unknown",
        "operatingSystem": {"macos": "unknown", "windows": "unknown"},
        "architecture": {"arm64": "unknown", "x86_64": "unknown"},
        "edition": {"free": declared, "studio": declared},
        "transport": {"embeddedFree": declared, "studioExternal": declared},
    }


def _clip_snapshot(conn: Any, name: str, key: str, *, project_id: str | None = None, third_party: bool = False, property_value: bool = False) -> dict[str, Any]:
    match = media_pool.find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Media Pool clip '{name}' was not found.")
    clip = match["clip"]
    native_token = sdk_live_inspection.media_pool_native_id(clip)
    public_id = (
        _sdk_native_id("media_pool_item_", project_id, native_token)
        if project_id and native_token
        else _native_id(clip, prefix="media_pool_item_", fallback=f"{match['folder']}:{name}")
    )
    if property_value:
        getter = getattr(clip, "GetClipProperty", None)
        if not callable(getter):
            raise APICallFailed("DaVinci Resolve clip-property readback is unavailable.")
        value = getter(key)
    elif third_party:
        value = media_pool.get_third_party_metadata(conn, name, key).get("value")
    else:
        value = media_pool.get_clip_metadata(conn, name, key)
    entity = {"kind": "clip", "id": public_id, "name": name, "folder": match["folder"]}
    return {"entity": entity, "value": value}


def _tree_byte_count(path: str) -> int:
    item = Path(path)
    if item.is_file():
        return item.stat().st_size
    if item.is_dir():
        return sum(child.stat().st_size for child in item.rglob("*") if child.is_file())
    raise APICallFailed("The expected preset artifact was not created.")


def _preset_names(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        raise APICallFailed("DaVinci Resolve preset-list readback is unavailable.")
    names = []
    for row in rows:
        if isinstance(row, str):
            names.append(row)
        elif isinstance(row, Mapping) and row.get("name"):
            names.append(str(row["name"]))
        else:
            raise APICallFailed("DaVinci Resolve returned a malformed preset list.")
    return sorted(names)


@dataclass(frozen=True)
class RenderPresetFileDescriptor:
    action_id: str
    operation_class = "mutation"
    version = 1

    @property
    def capability_id(self) -> str:
        return _CAPABILITY_IDS[self.action_id]

    @property
    def importing(self) -> bool:
        return self.action_id.endswith("import_preset") or self.action_id.endswith("burnin.import")

    @property
    def burnin(self) -> bool:
        return ".burnin." in self.action_id

    def validate_input(self, value: Any) -> dict[str, Any]:
        required = (
            ("sourceArtifactId",)
            if self.importing
            else ("presetName", "destinationArtifactId")
        )
        data = _text_object(value, required)
        artifact_id = data[
            "sourceArtifactId" if self.importing else "destinationArtifactId"
        ]
        if _ARTIFACT_ID.fullmatch(artifact_id) is None:
            raise ValidationError("Render preset action requires a managed artifact identity.")
        return data

    def _snapshot(self, value: Mapping[str, Any] | None = None) -> dict[str, Any]:
        conn = get_connection(require_project=True)
        if self.burnin:
            presets = _preset_names(render_engine.get_burnin_presets())
        else:
            getter = getattr(conn.project, "GetRenderPresetList", None)
            presets = _preset_names(getter() if callable(getter) else None)
        state = {"presets": presets, "protected": _project_protected_state(conn)}
        if value is not None:
            path = Path(value["inputPath" if self.importing else "outputPath"])
            if path.exists():
                stat = path.stat()
                state["artifact"] = {
                    "kind": "directory" if path.is_dir() else "file",
                    "device": str(stat.st_dev),
                    "inode": str(stat.st_ino),
                    "size": stat.st_size,
                    "mtimeNs": str(stat.st_mtime_ns),
                }
            else:
                state["artifact"] = {"kind": "absent"}
        return state

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        artifact_id = value[
            "sourceArtifactId" if self.importing else "destinationArtifactId"
        ]
        path = _managed_artifact_path(
            context,
            artifact_id,
            existing=self.importing,
            directory=False,
        )
        lowered = {
            **dict(value),
            "inputPath" if self.importing else "outputPath": path,
        }
        target = _project_target(context, value.get("presetName") or artifact_id)
        return {
            "targets": [target], "preState": self._snapshot(lowered),
            "impact": _specific_impact(context, self.action_id, value, target),
            "lowering": {"input": lowered},
            "verification": {"minimumEvidence": ["readback", "file" if not self.importing else "structural"]},
            "recovery": {"strategy": "remove_created_preset_when_supported_or_require_manual_recovery"},
        }

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        del context
        return {
            "targets": prepared["targets"],
            "preState": self._snapshot(prepared["lowering"]["input"]),
        }

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        del context
        conn = get_connection(require_project=True)
        value = prepared["lowering"]["input"]
        if self.action_id.endswith("render.import_preset"):
            return render_engine.import_render_preset(conn, value["inputPath"])
        if self.action_id.endswith("render.export_preset"):
            return render_engine.export_render_preset(conn, value["presetName"], value["outputPath"])
        if self.action_id.endswith("burnin.import"):
            return render_engine.import_burnin_preset(conn, value["inputPath"])
        return render_engine.export_burnin_preset(conn, value["presetName"], value["outputPath"])

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        del context
        after = self._snapshot()
        value = prepared["lowering"]["input"]
        if self.importing:
            added = sorted(set(after["presets"]) - set(prepared["preState"]["presets"]))
            expected = result.get("preset_name")
            if expected is None and len(added) == 1:
                expected = added[0]
            passed = bool(result.get("imported") and added == [expected])
            result["verifiedPresetName"] = expected
        else:
            byte_count = _tree_byte_count(value["outputPath"])
            passed = bool(result.get("exported") and byte_count >= 0)
            result["byteCount"] = byte_count
        passed = passed and after["protected"] == prepared["preState"]["protected"]
        result["after"] = after
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, result), "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del context, failure
        # Caller-visible exports and burn-in registrations are preserved after uncertainty.
        if not self.importing or self.burnin:
            return {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}
        return {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context
        value = prepared["lowering"]["input"]
        if self.importing:
            data = {
                "sourceArtifactId": value["sourceArtifactId"],
                "presetName": result["verifiedPresetName"],
                "imported": True,
            }
        else:
            data = {
                "presetName": value["presetName"],
                "artifactId": value["destinationArtifactId"],
                "byteCount": result["byteCount"],
            }
        return _assert_public({"actionId": self.action_id, "data": data})

    def validate_public_result(self, value: Any) -> bool:
        try:
            return value["actionId"] == self.action_id and set(value) == {"actionId", "data"}
        except Exception:
            return False


@dataclass(frozen=True)
class MediaMutationDescriptor:
    action_id: str
    operation_class = "mutation"
    version = 1

    @property
    def capability_id(self) -> str:
        return _CAPABILITY_IDS[self.action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
            if self.action_id.endswith("folders.create") and isinstance(value, Mapping) and "projectId" in value:
                if set(value) != {"projectId", "precondition", "parent", "name"} or not isinstance(value.get("parent"), Mapping):
                    raise ValidationError("Media Pool folder input does not match the semantic SDK contract.")
                parent = value["parent"]
                if set(parent) != ({"kind"} if parent.get("kind") == "root" else {"kind", "id"}):
                    raise ValidationError("Media Pool folder parent is invalid.")
                name_value = _text_object({"name": value["name"]}, ("name",))["name"]
                return {"projectId": value["projectId"], "precondition": value["precondition"], "parent": dict(parent), "name": name_value, "semantic": True}
            data = _text_object(value, ("path",))
            if data["path"].startswith(("/", "~")) or ".." in data["path"].split("/"):
                raise ValidationError("Media Pool folder path must be a logical relative path.")
            return data
        if self.action_id.endswith("media.metadata"):
            if isinstance(value, Mapping) and "projectId" in value:
                if set(value) != {"projectId", "precondition", "assetId", "entries"} or not isinstance(value.get("entries"), list):
                    raise ValidationError("Media Pool metadata input does not match the semantic SDK contract.")
                if not 1 <= len(value["entries"]) <= 12:
                    raise ValidationError("Media Pool metadata requires between one and twelve entries.")
                entries = []
                for entry in value["entries"]:
                    if not isinstance(entry, Mapping) or set(entry) != {"key", "value"}:
                        raise ValidationError("Media Pool metadata entry does not match the semantic SDK contract.")
                    key = _text_object({"key": entry["key"]}, ("key",))["key"]
                    if key not in _SEMANTIC_METADATA_NATIVE_KEYS:
                        raise ValidationError("Media Pool metadata key is outside the semantic SDK contract.")
                    entries.append({"key": key, "value": _literal_text(entry["value"], maximum=65_536)})
                if len({entry["key"] for entry in entries}) != len(entries):
                    raise ValidationError("Media Pool metadata keys must be unique.")
                return {
                    "projectId": value["projectId"], "precondition": value["precondition"],
                    "assetId": value["assetId"], "entries": entries, "semantic": True,
                }
            if not isinstance(value, Mapping) or set(value) != {"operation"} or not isinstance(value["operation"], Mapping):
                raise ValidationError("Media metadata input must contain one operation.")
            kind = value["operation"].get("kind")
            required = {
                "list": ("kind", "clipName"),
                "get": ("kind", "clipName", "key"),
                "set": ("kind", "clipName", "key", "value"),
            }.get(kind)
            if required is None:
                raise ValidationError("Media metadata operation kind is invalid.")
            if kind == "set":
                op = _text_object(
                    {key: item for key, item in value["operation"].items() if key != "value"},
                    tuple(key for key in required if key != "value"),
                )
                op["value"] = _literal_text(value["operation"].get("value"))
            else:
                op = _text_object(value["operation"], required)
            return {"operation": op}
        keys = ("clip", "key", "value") if self.action_id.endswith("third_party_metadata.set") else ("name", "key", "value")
        data = _text_object(
            {key: item for key, item in value.items() if key != "value"},
            tuple(key for key in keys if key != "value"),
        )
        data["value"] = _literal_text(value.get("value"))
        return data

    def _input(self, prepared: Mapping[str, Any]) -> tuple[str, str, str]:
        value = prepared["lowering"]["input"]
        if self.action_id.endswith("media.metadata"):
            op = value["operation"]
            return op["clipName"], op["key"], op["value"]
        return value.get("clip") or value.get("name"), value["key"], value["value"]

    def _lower(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if self.action_id.endswith("folders.create") and value.get("semantic") is True:
            conn = get_connection(require_project=True)
            parent = value["parent"]
            if parent["kind"] == "root":
                parent_path = conn.media_pool.GetRootFolder().GetName()
                parent_key = "root"
            else:
                _folder, parent_path = _folder_by_public_id(conn, value["projectId"], parent["id"])
                parent_key = parent["id"]
            return {**dict(value), "path": f"{parent_path}/{value['name']}", "targetBindingKey": f"{parent_key}:{value['name']}"}
        if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
            conn = get_connection(require_project=True)
            return {**dict(value), "path": _canonical_folder_path(conn, value["path"]), "targetBindingKey": value["path"]}
        if value.get("semantic") is not True:
            return dict(value)
        conn = get_connection(require_project=True)
        clip, folder = _clip_by_public_id(conn, value["projectId"], value["assetId"])
        return {**dict(value), "clipName": clip.GetName(), "folder": folder}

    def _snapshot(self, value: Mapping[str, Any]) -> dict[str, Any]:
        conn = get_connection(require_project=True)
        if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
            rows = _folder_snapshot(conn)
            target = next((row for row in rows if row["path"] == value["path"]), None)
            if self.action_id.endswith("folders.delete") and target and (target["clipCount"] or target["subfolderCount"]):
                raise ValidationError("Prepared folder deletion is limited to one empty folder.")
            return {"rows": rows, "protected": _project_protected_state(conn)}
        if value.get("semantic") is True:
            clip, folder = _clip_by_public_id(conn, value["projectId"], value["assetId"])
            getter = getattr(clip, "GetMetadata", None)
            if not callable(getter):
                raise APICallFailed("DaVinci Resolve clip-metadata readback is unavailable.")
            entity = {
                "kind": "clip",
                "id": value["assetId"],
                "name": clip.GetName(),
                "folder": folder,
            }
            return {
                "clip": entity,
                "values": {entry["key"]: getter(entry["key"]) for entry in value["entries"]},
                "protected": _project_protected_state(conn),
            }
        if self.action_id.endswith("media.metadata") and value.get("semantic") is not True and value["operation"]["kind"] in {"list", "get"}:
            name = value["operation"]["clipName"]
            match = media_pool.find_clip_match(conn, name)
            if not match:
                raise APICallFailed(f"Media Pool clip '{name}' was not found.")
            clip = match["clip"]
            getter = getattr(clip, "GetMetadata", None)
            if not callable(getter):
                raise APICallFailed("DaVinci Resolve clip-metadata readback is unavailable.")
            key = value["operation"].get("key")
            raw = getter(key) if key else getter()
            metadata = {key: raw} if key else dict(raw or {})
            native = sdk_live_inspection.media_pool_native_id(clip)
            entity_id = _sdk_native_id("media_pool_item_", value["projectId"], native) if native else _native_id(clip, prefix="media_pool_item_", fallback=f"{match['folder']}:{name}")
            return {"clip": {"entity": {"kind": "clip", "id": entity_id, "name": name, "folder": match["folder"]}, "metadata": metadata}, "protected": _project_protected_state(conn)}
        name = value["operation"]["clipName"] if self.action_id.endswith("media.metadata") else value.get("clip") or value.get("name")
        key = value["operation"]["key"] if self.action_id.endswith("media.metadata") else value["key"]
        return {"clip": _clip_snapshot(conn, name, key, project_id=value.get("projectId"), third_party=self.action_id.endswith("third_party_metadata.set"), property_value=self.action_id.endswith("property_set")), "protected": _project_protected_state(conn)}

    def _target(self, context: Mapping[str, Any], value: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
        project, _ = _project_binding(context)
        if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
            binding_key = value.get("targetBindingKey", value["path"])
            stable = _opaque("media_pool_folder_", f"{project['projectId']}:{binding_key}")
        else:
            stable = snapshot["clip"]["id"] if value.get("semantic") is True else snapshot["clip"]["entity"]["id"]
        exact = context.get("exactRequestBinding")
        identities = exact.get("identities") if isinstance(exact, Mapping) else None
        revisions = exact.get("revisions") if isinstance(exact, Mapping) else None
        target_ids = _carrier_array(identities.get("targetIds")) if isinstance(identities, Mapping) else None
        target_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
        if target_ids != [stable] or not isinstance(target_revisions, Mapping) or not isinstance(target_revisions.get(stable), str):
            raise ValidationError("Prepared Media Pool target drifted from carrier-owned identity custody.")
        return {"kind": "media_pool_target", "stableId": stable, "revision": target_revisions[stable]}

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        lowered = self._lower(value)
        project, _ = _project_binding(context)
        lowered.setdefault("projectId", project["projectId"])
        before = self._snapshot(lowered)
        if self.action_id.endswith("folders.create") and any(row["path"] == lowered["path"] for row in before["rows"]):
            raise ValidationError("Prepared folder creation requires an absent target folder.")
        if self.action_id.endswith("folders.delete") and not any(row["path"] == lowered["path"] for row in before["rows"]):
            raise ValidationError("Prepared folder deletion target does not exist.")
        target = self._target(context, lowered, before)
        return {"targets": [target], "preState": before, "impact": _specific_impact(context, self.action_id, value, target), "lowering": {"input": lowered}, "verification": {"minimumEvidence": ["readback", "structural"]}, "recovery": {"strategy": "restore_exact_media_value_or_require_manual_recovery"}}

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        return {"targets": prepared["targets"], "preState": self._snapshot(prepared["lowering"]["input"])}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        del context
        conn = get_connection(require_project=True)
        value = prepared["lowering"]["input"]
        if self.action_id.endswith("folders.create"):
            media_pool.create_folder(conn, value["path"])
            return {"target": {"kind": "folder", "path": value["path"]}}
        if self.action_id.endswith("folders.delete"):
            if media_pool.delete_folder(conn, value["path"]) is False:
                raise APICallFailed("DaVinci Resolve rejected the empty Media Pool folder deletion.")
            return {"target": {"kind": "folder", "path": value["path"]}}
        if self.action_id.endswith("media.metadata") and value.get("semantic") is not True and value["operation"]["kind"] in {"list", "get"}:
            return {"metadata": dict(prepared["preState"]["clip"]["metadata"])}
        if value.get("semantic") is True:
            clip, _folder = _clip_by_public_id(
                conn, value["projectId"], value["assetId"]
            )
            setter = getattr(clip, "SetMetadata", None)
            if not callable(setter):
                raise APICallFailed("DaVinci Resolve clip-metadata write is unavailable.")
            expected = {}
            for entry in value["entries"]:
                if setter(entry["key"], entry["value"]) is False:
                    raise APICallFailed("DaVinci Resolve rejected the clip-metadata write.")
                expected[entry["key"]] = entry["value"]
            return {"clip": value["clipName"], "metadata": expected, "updated": True}
        name, key, new_value = self._input(prepared)
        if self.action_id.endswith("third_party_metadata.set"):
            return media_pool.set_third_party_metadata(conn, name, key, new_value)
        if self.action_id.endswith("property_set"):
            match = media_pool.find_clip_match(conn, name)
            setter = getattr(match["clip"], "SetClipProperty", None) if match else None
            if not callable(setter) or setter(key, new_value) is False:
                raise APICallFailed("DaVinci Resolve rejected the clip-property write.")
            return {"target": {**prepared["preState"]["clip"]["entity"]}, "key": key, "value": new_value}
        media_pool.set_clip_metadata(conn, name, key, new_value)
        return {"clip": name, "metadata": {key: new_value}, "updated": True}

    def _readback(self, prepared: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        value = prepared["lowering"]["input"]
        after = self._snapshot(value)
        before = prepared["preState"]
        if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
            return after, {"before": before["rows"], "after": after["rows"], "protectedState": {"before": before["protected"], "after": after["protected"]}}
        if self.action_id.endswith("media.metadata") and value.get("semantic") is not True and value["operation"]["kind"] in {"list", "get"}:
            return after, {"before": before["clip"], "after": after["clip"], "protectedState": {"before": before["protected"], "after": after["protected"]}}
        if value.get("semantic") is True:
            target = before["clip"]

            def semantic_rows(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
                return [{**snapshot["clip"], "metadata": dict(snapshot["values"])}]

            protected_before = [{
                "entity": {
                    "kind": "media", "id": "media_pool_item_protected-state",
                    "name": "Protected state", "folder": target["folder"],
                },
                "fields": {"digest": _digest(before["protected"])},
            }]
            protected_after = [{
                "entity": {
                    "kind": "media", "id": "media_pool_item_protected-state",
                    "name": "Protected state", "folder": target["folder"],
                },
                "fields": {"digest": _digest(after["protected"])},
            }]
            return after, {
                "context": {"path": target["folder"], "target": target},
                "before": semantic_rows(before),
                "after": semantic_rows(after),
                "protectedState": {
                    "scope": target["folder"], "allowedTarget": target,
                    "before": protected_before, "after": protected_after,
                },
            }
        name, key, new_value = self._input(prepared)
        target = before["clip"]["entity"]
        def make(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
            return [
                {
                    **snapshot["clip"]["entity"],
                    "metadata": {key: snapshot["clip"]["value"]},
                }
            ]
        return after, {"context": {"path": target["folder"], "target": target}, "before": make(before), "after": make(after), "protectedState": {"scope": target["folder"], "allowedTarget": target, "before": [{"entity": {"kind": "media", "id": "media_pool_item_protected-state", "name": "Protected state", "folder": target["folder"]}, "fields": {"digest": _digest(before["protected"])}}], "after": [{"entity": {"kind": "media", "id": "media_pool_item_protected-state", "name": "Protected state", "folder": target["folder"]}, "fields": {"digest": _digest(after["protected"])}}]}}

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        del context
        after, readback = self._readback(prepared)
        value = prepared["lowering"]["input"]
        if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
            before_rows = prepared["preState"]["rows"]
            before_target = next((row for row in before_rows if row["path"] == value["path"]), None)
            after_target = next((row for row in after["rows"] if row["path"] == value["path"]), None)
            expected_after = self.action_id.endswith("folders.create")
            parent_path = value["path"].rsplit("/", 1)[0]
            before_parent = next((row for row in before_rows if row["path"] == parent_path), None)
            after_parent = next((row for row in after["rows"] if row["path"] == parent_path), None)
            def strip_mutated(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
                return [row for row in rows if row["path"] not in {value["path"], parent_path}]
            parent_delta = 1 if expected_after else -1
            passed = (
                (after_target is not None) == expected_after
                and strip_mutated(after["rows"]) == strip_mutated(before_rows)
                and before_parent is not None and after_parent is not None
                and after_parent["clipCount"] == before_parent["clipCount"]
                and after_parent["subfolderCount"] == before_parent["subfolderCount"] + parent_delta
                and after["protected"] == prepared["preState"]["protected"]
            )
            changed = (before_target is not None) != (after_target is not None)
        elif self.action_id.endswith("media.metadata") and value.get("semantic") is not True and value["operation"]["kind"] in {"list", "get"}:
            passed = after == prepared["preState"]
            changed = False
        elif value.get("semantic") is True:
            expected = {entry["key"]: entry["value"] for entry in value["entries"]}
            passed = (
                after["clip"] == prepared["preState"]["clip"]
                and after["values"] == expected
                and after["protected"] == prepared["preState"]["protected"]
            )
            changed = prepared["preState"]["values"] != after["values"]
        else:
            _name, _key, expected = self._input(prepared)
            passed = (
                after["clip"]["entity"] == prepared["preState"]["clip"]["entity"]
                and after["clip"]["value"] == expected
                and after["protected"] == prepared["preState"]["protected"]
            )
            changed = prepared["preState"]["clip"]["value"] != after["clip"]["value"]
        if passed and value.get("semantic") is not True:
            target_id = prepared["targets"][0]["stableId"]
            if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
                parts = value["path"].split("/")
                data = {"outcome": self.action_id.removeprefix("cutagent.action.media."), "folder": {
                    "kind": "media_folder", "id": target_id, "addressability": "addressable",
                    "name": parts[-1], "folderName": "/".join(parts[:-1]) or "Media Pool root",
                }}
            elif self.action_id.endswith("media.metadata") and value.get("semantic") is not True and value["operation"]["kind"] in {"list", "get"}:
                entity = after["clip"]["entity"]
                data = {"outcome": self.action_id.removeprefix("cutagent.action.media."), "item": {
                    "kind": "media_asset", "id": entity["id"], "addressability": "addressable",
                    "name": entity["name"], "folderName": entity["folder"],
                }, "metadata": [{"key": key, "value": metadata_value} for key, metadata_value in sorted(after["clip"]["metadata"].items())]}
            else:
                entity = after["clip"]["entity"]
                data = {"outcome": self.action_id.removeprefix("cutagent.action.media."), "item": {
                    "kind": "media_asset", "id": entity["id"], "addressability": "addressable",
                    "name": entity["name"], "folderName": entity["folder"],
                }, "metadata": [{"key": self._input(prepared)[1], "value": self._input(prepared)[2]}]}
            result["public"] = {
                "actionId": self.action_id,
                "applicability": _media_applicability(),
                "payload": {
                    "status": "completed" if changed else "no_op", "changed": changed, "data": data,
                    "verification": {"outcome": "passed", "evidence": [{"kind": "structural_readback", "summary": "Exact target and protected state matched independent readback."}], "protectedState": "preserved"},
                },
            }
        result["after"] = after
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, readback), "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del context, failure
        restored = False
        try:
            conn = get_connection(require_project=True)
            value = prepared["lowering"]["input"]
            if self.action_id.endswith("media.metadata") and value.get("semantic") is not True and value["operation"]["kind"] in {"list", "get"}:
                return {"outcome": "not_needed", "attempted": False, "manualActionRequired": False}
            if self.action_id.endswith("folders.create"):
                before_target = next((row for row in prepared["preState"]["rows"] if row["path"] == value["path"]), None)
                current_target = next((row for row in _folder_snapshot(conn) if row["path"] == value["path"]), None)
                restored = before_target is None and current_target is not None and not current_target["clipCount"] and not current_target["subfolderCount"] and media_pool.delete_folder(conn, value["path"])
            elif self.action_id.endswith("folders.delete"):
                restored = bool(media_pool.create_folder(conn, value["path"]))
            elif value.get("semantic") is True:
                clip, _folder = _clip_by_public_id(
                    conn, value["projectId"], value["assetId"]
                )
                setter = getattr(clip, "SetMetadata", None)
                if not callable(setter):
                    raise APICallFailed("DaVinci Resolve clip-metadata write is unavailable.")
                for metadata_key, old_value in prepared["preState"]["values"].items():
                    if setter(metadata_key, old_value) is False:
                        raise APICallFailed("DaVinci Resolve rejected the clip-metadata recovery write.")
                restored = True
                name, key, previous = value["clipName"], "", None
            else:
                name, key, _ = self._input(prepared)
                previous = prepared["preState"]["clip"]["value"]
            if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
                pass
            elif self.action_id.endswith("third_party_metadata.set"):
                media_pool.set_third_party_metadata(conn, name, key, previous)
            elif self.action_id.endswith("property_set"):
                match = media_pool.find_clip_match(conn, name)
                restored = bool(match and match["clip"].SetClipProperty(key, previous) is not False)
            elif value.get("semantic") is not True:
                restored = media_pool.set_clip_metadata(conn, name, key, previous)
            if not self.action_id.endswith("property_set"):
                restored = True
            restored = bool(restored and self._snapshot(value) == prepared["preState"])
        except Exception:
            restored = False
        return {"outcome": "succeeded" if restored else "manual_required", "attempted": True, "manualActionRequired": not restored}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        value = prepared["lowering"]["input"]
        if self.action_id.endswith("folders.create") and value.get("semantic") is True:
            conn = get_connection(require_project=True)
            folder, path = next((item for item in _walk_media_folders(conn.media_pool.GetRootFolder()) if item[1] == value["path"]), (None, None))
            if folder is None:
                raise APICallFailed("Created Media Pool folder is unavailable during result projection.")
            revision = f"revision_{_digest(result['after'])[7:]}"
            native = _native_token(folder)
            return _assert_public({
                "projectId": value["projectId"],
                "folder": {
                    "id": _sdk_native_id("media_pool_folder_", value["projectId"], native) if native else None,
                    "snapshotId": _opaque("snapshot_media_pool_folder_", f"{revision}:{path}"),
                    "name": value["name"],
                },
                "revision": revision,
            })
        if value.get("semantic") is True:
            revision = f"revision_{_digest(result['after'])[7:]}"
            return _assert_public({
                "projectId": value["projectId"],
                "assetId": value["assetId"],
                "entries": value["entries"],
                "revision": revision,
            })
        return _assert_public(result["public"])

    def validate_public_result(self, value: Any) -> bool:
        try:
            if "actionId" not in value:
                if self.action_id.endswith("folders.create"):
                    folder = value.get("folder")
                    return (
                        set(value) == {"projectId", "folder", "revision"}
                        and isinstance(value["projectId"], str)
                        and isinstance(value["revision"], str) and value["revision"].startswith("revision_")
                        and isinstance(folder, Mapping) and set(folder) == {"id", "snapshotId", "name"}
                        and (folder["id"] is None or isinstance(folder["id"], str) and folder["id"].startswith("media_pool_folder_"))
                        and isinstance(folder["snapshotId"], str) and folder["snapshotId"].startswith("snapshot_media_pool_folder_")
                        and isinstance(folder["name"], str) and bool(folder["name"])
                    )
                if self.action_id.endswith("media.metadata"):
                    return (
                        set(value) == {"projectId", "assetId", "entries", "revision"}
                        and isinstance(value["projectId"], str)
                        and isinstance(value["assetId"], str) and value["assetId"].startswith("media_pool_item_")
                        and isinstance(value["revision"], str) and value["revision"].startswith("revision_")
                        and isinstance(value["entries"], list) and 1 <= len(value["entries"]) <= 12
                        and all(isinstance(entry, Mapping) and set(entry) == {"key", "value"} and isinstance(entry["key"], str) and isinstance(entry["value"], str) for entry in value["entries"])
                    )
            from ..sdk_action_descriptors.residual_av_prepared_action import (
                _schema as public_action_schema,
                _validate_schema as validate_public_action_schema,
            )
            validate_public_action_schema(value, public_action_schema(self.action_id, "result"))
            return value["payload"]["status"] in {"completed", "no_op"}
        except Exception:
            return False


@dataclass(frozen=True)
class BoundMediaMutationDescriptor(MediaMutationDescriptor):
    """Media mutation lifecycle bound to authoritative pool identity and revision."""

    def _bound_input(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        project, _ = _project_binding(context)
        project_id = project["projectId"]
        if value.get("projectId", project_id) != project_id:
            raise ValidationError("Prepared Media Pool input belongs to another project.")
        binding = _private_media_binding(context)
        conn = get_connection(require_project=True)
        _assert_native_project_binding(context, conn)
        state = _media_state(conn, project_id)
        if state["revision"] != binding["revision"]:
            raise ValidationError("Prepared Media Pool revision changed after carrier capture.")
        lowered = {**dict(value), "projectId": project_id, "binding": binding}
        if self.action_id.endswith("folders.create"):
            if binding["operation"] != "create" or not isinstance(binding["parentId"], str) or binding["targetId"] is not None:
                raise ValidationError("Prepared folder creation has malformed exact parent binding.")
            parent, parent_path = _folder_by_public_id(conn, project_id, binding["parentId"])
            del parent
            if binding["targetPath"] != f"{parent_path}/{binding['targetName']}":
                raise ValidationError("Prepared folder creation parent/path binding drifted.")
            if any(row["path"] == binding["targetPath"] for row in state["folders"]):
                raise ValidationError("Prepared folder creation requires an absent exact target.")
            if value.get("semantic") is True and value["name"] != binding["targetName"]:
                raise ValidationError("Prepared folder creation name drifted from carrier capture.")
            lowered.update({"path": binding["targetPath"], "name": binding["targetName"]})
            return lowered
        if self.action_id.endswith("folders.delete"):
            if binding["operation"] != "delete" or not isinstance(binding["targetId"], str):
                raise ValidationError("Prepared folder deletion has malformed exact target binding.")
            folder, actual_path = _folder_by_public_id(conn, project_id, binding["targetId"])
            if actual_path != binding["targetPath"] or folder.GetName() != binding["targetName"]:
                raise ValidationError("Prepared folder deletion target identity/path drifted.")
            if folder.GetClipList() or folder.GetSubFolderList():
                raise ValidationError("Prepared folder deletion is limited to the exact empty folder.")
            lowered.update({"path": actual_path, "name": folder.GetName()})
            return lowered
        if binding["operation"] != "asset" or not isinstance(binding["targetId"], str):
            raise ValidationError("Prepared Media Pool asset has malformed exact target binding.")
        clip, folder = _clip_by_public_id(conn, project_id, binding["targetId"])
        if value.get("semantic") is True and value.get("assetId") != binding["targetId"]:
            raise ValidationError("Prepared semantic Media Pool asset identity drifted.")
        requested_name = value.get("operation", {}).get("clipName") or value.get("name") or value.get("clip")
        if requested_name is not None and requested_name != binding["targetName"]:
            raise ValidationError("Prepared named Media Pool target drifted from carrier capture.")
        lowered.update({"assetId": binding["targetId"], "clipName": clip.GetName(), "folder": folder})
        return lowered

    def _snapshot_bound(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        conn = get_connection(require_project=True)
        state = _media_state(conn, value["projectId"])
        project_protected = _project_protected_state(conn, context)
        if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
            return {
                "rows": state["folders"],
                "mediaRevision": state["revision"],
                "protectedAssets": state["assets"],
                "protectedProject": project_protected,
            }
        target = next((row for row in state["assets"] if row["id"] == value["assetId"]), None)
        if target is None:
            raise ValidationError("Prepared Media Pool asset disappeared before readback.")
        entity = {"kind": "clip", "id": target["id"], "name": target["name"], "folder": target["folder"]}
        if self.action_id.endswith("media.metadata"):
            if value.get("semantic") is True:
                keys = tuple(entry["key"] for entry in value["entries"])
                return {
                    "clip": entity,
                    "values": {
                        key: _casefold_value(target[field_kind], native_key)
                        for key in keys
                        for field_kind, native_key in [_semantic_metadata_location(key)]
                    },
                    "mediaRevision": state["revision"],
                    "protectedMedia": _protected_semantic_media_state(state, target["id"], keys),
                    "protectedProject": project_protected,
                }
            operation = value["operation"]
            if operation["kind"] in {"list", "get"}:
                key = operation.get("key")
                metadata = dict(target["metadata"]) if key is None else {key: _casefold_value(target["metadata"], key)}
                return {"clip": {"entity": entity, "metadata": metadata}, "mediaRevision": state["revision"], "protectedMedia": _protected_media_state(state), "protectedProject": project_protected}
            key = operation["key"]
            field_kind = "metadata"
        elif self.action_id.endswith("third_party_metadata.set"):
            key = value["key"]
            field_kind = "thirdPartyMetadata"
        else:
            key = value["key"]
            field_kind = "properties"
        return {
            "clip": {"entity": entity, "value": _casefold_value(target[field_kind], key)},
            "mediaRevision": state["revision"],
            "protectedMedia": _protected_media_state(state, target_id=target["id"], field_kind=field_kind, allowed_keys=(key,)),
            "protectedProject": project_protected,
        }

    def _target_bound(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        binding = value["binding"]
        stable_id = binding["parentId"] if binding["operation"] == "create" else binding["targetId"]
        exact = context.get("exactRequestBinding")
        identities = exact.get("identities") if isinstance(exact, Mapping) else None
        revisions = exact.get("revisions") if isinstance(exact, Mapping) else None
        target_ids = _carrier_array(identities.get("targetIds")) if isinstance(identities, Mapping) else None
        target_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
        if target_ids != [stable_id] or not isinstance(target_revisions, Mapping) or target_revisions.get(stable_id) != binding["revision"]:
            raise ValidationError("Prepared Media Pool target/revision drifted from carrier custody.")
        return {"kind": "media_pool_target", "stableId": stable_id, "revision": binding["revision"]}

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        lowered = self._bound_input(context, value)
        before = self._snapshot_bound(context, lowered)
        if before["mediaRevision"] != lowered["binding"]["revision"]:
            raise ValidationError("Prepared Media Pool changed during descriptor preparation.")
        target = self._target_bound(context, lowered)
        return {
            "targets": [target], "preState": before,
            "impact": _specific_impact(context, self.action_id, value, target),
            "lowering": {"input": lowered},
            "verification": {"minimumEvidence": ["readback", "structural"]},
            "recovery": {"strategy": "restore_exact_asset_value_or_require_manual_folder_recovery"},
        }

    def _revalidate(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        value = self._bound_input(context, prepared["lowering"]["input"])
        current = self._snapshot_bound(context, value)
        if current["mediaRevision"] != prepared["preState"]["mediaRevision"]:
            raise ValidationError("Prepared Media Pool changed before execution.")
        return value

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        value = self._revalidate(context, prepared)
        return {"targets": prepared["targets"], "preState": self._snapshot_bound(context, value)}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        value = self._revalidate(context, prepared)
        conn = get_connection(require_project=True)
        if self.action_id.endswith("folders.create"):
            parent, _ = _folder_by_public_id(conn, value["projectId"], value["binding"]["parentId"])
            creator = getattr(conn.media_pool, "AddSubFolder", None)
            created = creator(parent, value["name"]) if callable(creator) else None
            if not created:
                raise APICallFailed("DaVinci Resolve rejected exact Media Pool folder creation.")
            native = _native_token(created)
            if not native:
                raise APICallFailed("Created Media Pool folder has no durable native identity.")
            return {"createdId": _sdk_native_id("media_pool_folder_", value["projectId"], native)}
        if self.action_id.endswith("folders.delete"):
            folder, _ = _folder_by_public_id(conn, value["projectId"], value["binding"]["targetId"])
            deleter = getattr(conn.media_pool, "DeleteFolders", None)
            if not callable(deleter) or deleter([folder]) is False:
                raise APICallFailed("DaVinci Resolve rejected exact empty Media Pool folder deletion.")
            return {"deletedId": value["binding"]["targetId"]}
        clip, _ = _clip_by_public_id(conn, value["projectId"], value["assetId"])
        if self.action_id.endswith("media.metadata") and value.get("semantic") is not True and value["operation"]["kind"] in {"list", "get"}:
            return {"metadata": dict(prepared["preState"]["clip"]["metadata"])}
        if self.action_id.endswith("media.metadata"):
            if value.get("semantic") is True:
                entries = [
                    {"fieldKind": _semantic_metadata_location(entry["key"])[0], "key": _semantic_metadata_location(entry["key"])[1], "value": entry["value"]}
                    for entry in value["entries"]
                ]
                for entry in entries:
                    setter = getattr(clip, "SetClipProperty" if entry["fieldKind"] == "properties" else "SetMetadata", None)
                    if not callable(setter) or setter(entry["key"], entry["value"]) is False:
                        raise APICallFailed("DaVinci Resolve rejected the exact Media Pool field write.")
                return {"assetId": value["assetId"], "entries": entries}
            entries = [{"key": value["operation"]["key"], "value": value["operation"]["value"]}]
            setter = getattr(clip, "SetMetadata", None)
        elif self.action_id.endswith("third_party_metadata.set"):
            entries = [{"key": value["key"], "value": value["value"]}]
            setter = getattr(clip, "SetThirdPartyMetadata", None)
        else:
            entries = [{"key": value["key"], "value": value["value"]}]
            setter = getattr(clip, "SetClipProperty", None)
        if not callable(setter):
            raise APICallFailed("DaVinci Resolve Media Pool field write is unavailable.")
        for entry in entries:
            if setter(entry["key"], entry["value"]) is False:
                raise APICallFailed("DaVinci Resolve rejected the exact Media Pool field write.")
        return {"assetId": value["assetId"], "entries": entries}

    def _readback_bound(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        return self._snapshot_bound(context, prepared["lowering"]["input"])

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        value = prepared["lowering"]["input"]
        before = prepared["preState"]
        after = self._readback_bound(context, prepared)
        if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
            before_rows = before["rows"]
            before_target = next((row for row in before_rows if row["path"] == value["path"]), None)
            after_target = next((row for row in after["rows"] if row["path"] == value["path"]), None)
            creating = self.action_id.endswith("folders.create")
            parent_path = value["path"].rsplit("/", 1)[0]
            def strip_mutated(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
                return [row for row in rows if row["path"] not in {value["path"], parent_path}]
            before_parent = next((row for row in before_rows if row["path"] == parent_path), None)
            after_parent = next((row for row in after["rows"] if row["path"] == parent_path), None)
            identity_ok = (
                creating
                and before_target is None
                and after_target is not None
                and after_target["id"] == result.get("createdId")
            ) or (
                not creating
                and before_target is not None
                and before_target["id"] == value["binding"]["targetId"]
                and after_target is None
                and result.get("deletedId") == value["binding"]["targetId"]
            )
            passed = bool(
                identity_ok
                and strip_mutated(after["rows"]) == strip_mutated(before_rows)
                and before_parent is not None and after_parent is not None
                and after_parent["id"] == before_parent["id"]
                and after_parent["clipCount"] == before_parent["clipCount"]
                and after_parent["subfolderCount"] == before_parent["subfolderCount"] + (1 if creating else -1)
                and after["protectedAssets"] == before["protectedAssets"]
                and after["protectedProject"] == before["protectedProject"]
            )
            changed = True
        elif self.action_id.endswith("media.metadata") and value.get("semantic") is not True and value["operation"]["kind"] in {"list", "get"}:
            passed = after == before
            changed = False
        elif value.get("semantic") is True:
            expected = {entry["key"]: entry["value"] for entry in value["entries"]}
            passed = after["clip"]["id"] == before["clip"]["id"] and after["values"] == expected and after["protectedMedia"] == before["protectedMedia"] and after["protectedProject"] == before["protectedProject"]
            changed = before["values"] != after["values"]
        else:
            _name, _key, expected = self._input(prepared)
            passed = after["clip"]["entity"]["id"] == before["clip"]["entity"]["id"] and after["clip"]["value"] == expected and after["protectedMedia"] == before["protectedMedia"] and after["protectedProject"] == before["protectedProject"]
            changed = before["clip"]["value"] != after["clip"]["value"]
        # The authoritative Media Pool revision covers the public inspection
        # projection. Folder topology is always part of that projection, while
        # arbitrary clip properties and third-party/private metadata are not.
        # Exact field readback below proves those writes without inventing a
        # descriptor-local revision or requiring unrelated public state to move.
        if (self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete")) and changed and after["mediaRevision"] == before["mediaRevision"]:
            passed = False
        if passed and value.get("semantic") is not True:
            if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
                data = {"outcome": self.action_id.removeprefix("cutagent.action.media."), "folder": {"kind": "media_folder", "id": result.get("createdId") or result.get("deletedId"), "addressability": "addressable", "name": value["name"], "folderName": value["path"].rsplit("/", 1)[0]}}
            elif self.action_id.endswith("media.metadata") and value["operation"]["kind"] in {"list", "get"}:
                entity = after["clip"]["entity"]
                data = {"outcome": "metadata", "item": {"kind": "media_asset", "id": entity["id"], "addressability": "addressable", "name": entity["name"], "folderName": entity["folder"]}, "metadata": [{"key": key, "value": item} for key, item in sorted(after["clip"]["metadata"].items())]}
            else:
                entity = after["clip"]["entity"]
                data = {"outcome": self.action_id.removeprefix("cutagent.action.media."), "item": {"kind": "media_asset", "id": entity["id"], "addressability": "addressable", "name": entity["name"], "folderName": entity["folder"]}, "metadata": [{"key": self._input(prepared)[1], "value": self._input(prepared)[2]}]}
            result["public"] = {"actionId": self.action_id, "applicability": _media_applicability(), "payload": {"status": "completed" if changed else "no_op", "changed": changed, "data": data, "verification": {"outcome": "passed", "evidence": [{"kind": "structural_readback", "summary": "Exact Media Pool target, revision, and protected state matched readback."}], "protectedState": "preserved"}}}
        result["after"] = after
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, {"beforeRevision": before["mediaRevision"], "afterRevision": after["mediaRevision"]}), "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        value = prepared["lowering"]["input"]
        if self.action_id.endswith("folders.create") or self.action_id.endswith("folders.delete"):
            return {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}
        if self.action_id.endswith("media.metadata") and value.get("semantic") is not True and value["operation"]["kind"] in {"list", "get"}:
            return {"outcome": "not_needed", "attempted": False, "manualActionRequired": False}
        try:
            conn = get_connection(require_project=True)
            _assert_native_project_binding(context, conn)
            clip, _ = _clip_by_public_id(conn, value["projectId"], value["assetId"])
            if value.get("semantic") is True:
                previous = [(*_semantic_metadata_location(key), old) for key, old in prepared["preState"]["values"].items()]
                if any(
                    not callable(setter := getattr(clip, "SetClipProperty" if field_kind == "properties" else "SetMetadata", None))
                    or setter(native_key, old) is False
                    for field_kind, native_key, old in previous
                ):
                    raise APICallFailed("DaVinci Resolve rejected exact Media Pool recovery.")
            elif self.action_id.endswith("third_party_metadata.set"):
                setter = getattr(clip, "SetThirdPartyMetadata", None)
                previous = {value["key"]: prepared["preState"]["clip"]["value"]}
            elif self.action_id.endswith("property_set"):
                setter = getattr(clip, "SetClipProperty", None)
                previous = {value["key"]: prepared["preState"]["clip"]["value"]}
            else:
                setter = getattr(clip, "SetMetadata", None)
                previous = {value["operation"]["key"]: prepared["preState"]["clip"]["value"]}
            if value.get("semantic") is not True and (
                not callable(setter) or any(setter(key, old) is False for key, old in previous.items())
            ):
                raise APICallFailed("DaVinci Resolve rejected exact Media Pool recovery.")
            restored = self._snapshot_bound(context, value)
            if value.get("semantic") is True:
                exact = restored["values"] == prepared["preState"]["values"]
            else:
                exact = restored["clip"]["value"] == prepared["preState"]["clip"]["value"]
            exact = exact and restored["protectedMedia"] == prepared["preState"]["protectedMedia"] and restored["protectedProject"] == prepared["preState"]["protectedProject"]
            return {"outcome": "succeeded" if exact else "manual_required", "attempted": True, "manualActionRequired": not exact}
        except Exception:
            return {"outcome": "manual_required", "attempted": True, "manualActionRequired": True}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context
        value = prepared["lowering"]["input"]
        revision = result["after"]["mediaRevision"]
        if self.action_id.endswith("folders.create") and value.get("semantic") is True:
            return _assert_public({"projectId": value["projectId"], "folder": {"id": result["createdId"], "snapshotId": _sdk_digest("snapshot_media_pool_folder_", {"revision": revision, "stableId": result["createdId"]}), "name": value["name"]}, "revision": revision})
        if value.get("semantic") is True:
            return _assert_public({"projectId": value["projectId"], "assetId": value["assetId"], "entries": value["entries"], "revision": revision})
        return _assert_public(result["public"])


def _project_descriptors() -> dict[str, ProjectLifecycleDescriptor]:
    def text(required: tuple[str, ...], optional: tuple[str, ...] = ()) -> Callable[[Any], Mapping[str, Any]]:
        return lambda value: _text_object(value, required, optional)

    def library_create(value: Any) -> Mapping[str, Any]:
        data = _text_object(value, ("libraryName", "directoryPath"), ("precondition",))
        data["directoryPath"] = _absolute_path(data["directoryPath"], must_exist=False, destination=True)
        if "precondition" in data:
            data["semantic"] = True
        return data

    def library_switch(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping) and isinstance(value.get("library"), Mapping):
            if set(value) != {"library", "precondition"}:
                raise ValidationError("Project-library switch input does not match the semantic SDK contract.")
            library = _text_object(value["library"], ("name", "kind"))
            if library["kind"] != "disk":
                raise ValidationError("Only Disk project libraries can be opened.")
            return {"libraryName": library["name"], "libraryKind": "disk", "precondition": value["precondition"], "semantic": True}
        return _text_object(value, ("libraryName",), ("libraryKind",))

    def project_open(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping) and isinstance(value.get("project"), Mapping):
            if set(value) != {"project", "precondition"}:
                raise ValidationError("Project-open input does not match the semantic SDK contract.")
            project = _text_object(value["project"], ("id", "name"))
            return {"name": project["name"], "projectId": project["id"], "precondition": value["precondition"], "semantic": True}
        return _text_object(value, ("name",))

    def project_export(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping) and isinstance(value.get("project"), Mapping):
            if not set(value) <= {"project", "precondition", "destinationArtifactId", "withStills"}:
                raise ValidationError("Project-export input does not match the semantic SDK contract.")
            project = _text_object(value["project"], ("id", "name"))
            return {"name": project["name"], "projectId": project["id"], **{key: value[key] for key in value if key != "project"}, "semantic": True}
        return artifact_input(value, ("name", "destinationArtifactId"), ("projectId", "precondition", "withStills"))

    def library_backup(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping) and isinstance(value.get("library"), Mapping):
            if not set(value) <= {"library", "precondition", "destinationArtifactId"}:
                raise ValidationError("Project-library backup input does not match the semantic SDK contract.")
            library = _text_object(value["library"], ("name", "kind"))
            if library["kind"] != "disk":
                raise ValidationError("Only Disk project libraries can be backed up.")
            return {"libraryName": library["name"], **{key: value[key] for key in value if key != "library"}, "semantic": True}
        return artifact_input(value, ("libraryName", "destinationArtifactId"), ("precondition",))

    def artifact_input(value: Any, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> Mapping[str, Any]:
        data = _text_object(value, required, optional)
        if "precondition" in data:
            data["semantic"] = True
        return data

    specs: dict[str, Callable[[Any], Mapping[str, Any]]] = {
        "cutagent.action.project.export": project_export,
        "cutagent.action.project.library.backup": library_backup,
        "cutagent.action.project.library.create": library_create,
        "cutagent.action.project.library.restore": lambda value: artifact_input(value, ("libraryName", "directoryPath", "sourceArtifactId"), ("precondition",)),
        "cutagent.action.project.library.switch": library_switch,
        "cutagent.action.project.open": project_open,
        "cutagent.action.project.restore": lambda value: artifact_input(value, ("sourceArtifactId", "name"), ("precondition",)),
        "cutagent.action.project.import": lambda value: artifact_input(value, ("sourceArtifactId", "name")),
        "cutagent.action.project.delete": text(("name",)),
    }
    return {action_id: ProjectLifecycleDescriptor(action_id, normalize) for action_id, normalize in specs.items()}


PROJECT_RUNTIME_ACTION_IDS: tuple[str, ...] = (
    "cutagent.action.project.archive",
    "cutagent.action.project.cleanup_scratch",
    "cutagent.action.project.close",
    "cutagent.action.project.cloud.create",
    "cutagent.action.project.cloud.import",
    "cutagent.action.project.cloud.open",
    "cutagent.action.project.cloud.restore",
    "cutagent.action.project.delete",
    "cutagent.action.project.export",
    "cutagent.action.project.folders.create",
    "cutagent.action.project.folders.delete",
    "cutagent.action.project.folders.open",
    "cutagent.action.project.folders.root",
    "cutagent.action.project.folders.up",
    "cutagent.action.project.import",
    "cutagent.action.project.library.backup",
    "cutagent.action.project.library.create",
    "cutagent.action.project.library.restore",
    "cutagent.action.project.library.switch",
    "cutagent.action.project.open",
    "cutagent.action.project.preset.load",
    "cutagent.action.project.preset.save",
    "cutagent.action.project.restore",
    "cutagent.action.project.save",
)


EXTENDED_PROJECT_MEDIA_CALLABLE_ACTION_IDS: tuple[str, ...] = (
    "cutagent.action.media.folders.create",
    "cutagent.action.media.folders.delete",
    "cutagent.action.media.metadata",
    "cutagent.action.media.property_set",
    "cutagent.action.media.third_party_metadata.set",
    *PROJECT_RUNTIME_ACTION_IDS,
)


def extended_project_media_prepared_action_descriptors() -> dict[str, Any]:
    descriptors: dict[str, Any] = {
        **_project_descriptors(),
        ProjectCleanupScratchDescriptor.action_id: ProjectCleanupScratchDescriptor(),
        ProjectArchiveDescriptor.action_id: ProjectArchiveDescriptor(),
        ProjectCloseDescriptor.action_id: ProjectCloseDescriptor(),
        **{
            action_id: ProjectFolderDescriptor(action_id)
            for action_id in PROJECT_RUNTIME_ACTION_IDS
            if ".folders." in action_id
        },
        **{
            action_id: ProjectContextDescriptor(action_id)
            for action_id in PROJECT_RUNTIME_ACTION_IDS
            if ".cloud." in action_id or ".preset." in action_id or action_id.endswith("project.save")
        },
        **{
            action_id: BoundMediaMutationDescriptor(action_id)
            for action_id in EXTENDED_PROJECT_MEDIA_CALLABLE_ACTION_IDS
            if action_id.startswith("cutagent.action.media.")
        },
    }
    if set(descriptors) != set(EXTENDED_PROJECT_MEDIA_CALLABLE_ACTION_IDS):
        raise RuntimeError("Extended project/media prepared-action contribution is incomplete.")
    return descriptors
