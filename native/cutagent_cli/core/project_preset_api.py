"""Strict documented project-settings preset operations."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

from ..errors import APICallFailed, CapabilityNegotiationFailed, ValidationError

SAVE_METHODS = ("SaveCurrentProjectSettingsAsNewPreset", "SavePreset", "SaveAsPreset", "CreatePreset")
_METHODS = {
    "list": ("GetProjectSettingsPresetList", "GetPresetList"),
    "load": ("SetProjectSettingsPreset", "SetPreset"),
    "delete": ("DeleteProjectSettingsPreset", "DeletePreset"),
}
_MAX_BYTES = 16 * 1024 * 1024


def preset_method(project: Any, operation: str):
    """Prefer 21.1 methods; never retry a rejected mutation on another route."""
    modern, legacy = _METHODS[operation]
    fn = getattr(project, modern, None)
    if callable(fn):
        if operation == "list":
            return fn
        def by_name(value: Any):
            return fn(value["Name"] if isinstance(value, Mapping) else value)
        by_name.native_preset_api = True
        return by_name
    fn = getattr(project, legacy, None)
    return fn if callable(fn) else None


def _name(value: Any, *, native: bool) -> str:
    error = APICallFailed if native else ValidationError
    if not isinstance(value, str) or not value or len(value) > 1024 or "\x00" in value:
        raise error("Project preset name must be a bounded nonempty string.")
    return value


def requested_project_preset_name(value: Any) -> str:
    return _name(value, native=False)


def project_preset_records(project: Any) -> list[dict[str, Any]]:
    getter = preset_method(project, "list")
    raw = getter() if callable(getter) else None
    if not isinstance(raw, list):
        raise APICallFailed("DaVinci Resolve project preset readback is unavailable.")
    result = []
    names = []
    for item in raw:
        if isinstance(item, Mapping):
            record = deepcopy(dict(item))
            preset_name = _name(record.get("Name"), native=True)
        elif isinstance(item, str):
            preset_name = _name(item, native=True)
            record = {"Name": preset_name}
        else:
            raise APICallFailed("DaVinci Resolve returned an invalid project preset record.")
        names.append(preset_name)
        result.append({"name": preset_name, "record": record})
    if len(set(names)) != len(names):
        raise APICallFailed("DaVinci Resolve returned an ambiguous project preset list.")
    return result


def project_preset_names_ordered(project: Any) -> list[str]:
    return [item["name"] for item in project_preset_records(project)]


def project_preset_names(project: Any) -> set[str]:
    return set(project_preset_names_ordered(project))


def _settings(project: Any) -> dict[str, Any]:
    getter = getattr(project, "GetSetting", None)
    raw = getter() if callable(getter) else None
    if not isinstance(raw, Mapping):
        raise APICallFailed("DaVinci Resolve project settings readback is unavailable.")
    return deepcopy(dict(raw))


def _unique(records: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [item for item in records if item["name"] == name]
    if len(matches) != 1:
        raise APICallFailed("DaVinci Resolve project preset target is missing or ambiguous.", details={"preset_name": name, "matching_entries": len(matches), "available_presets": [item["name"] for item in records]})
    return matches[0]


def _single_insertion(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> str | None:
    if len(after) != len(before) + 1:
        return None
    candidates = [after[i]["name"] for i in range(len(after)) if after[:i] + after[i + 1:] == before]
    distinct = set(candidates)
    added = next(iter(distinct)) if len(distinct) == 1 else None
    return added if added not in {item["name"] for item in before} else None


def _catalog_preserved_after_load(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    before_settings: Mapping[str, Any],
    after_settings: Mapping[str, Any],
) -> bool:
    """Allow only the documented dynamic resolution fields of Current Project."""
    if after == before:
        return True
    if len(after) != len(before) or [row["name"] for row in after] != [row["name"] for row in before]:
        return False
    current_indexes = [index for index, row in enumerate(before) if row["name"] == "Current Project"]
    if len(current_indexes) != 1:
        return False
    current_index = current_indexes[0]
    for index, (before_row, after_row) in enumerate(zip(before, after, strict=True)):
        if index != current_index:
            if after_row != before_row:
                return False
            continue
        before_record = before_row["record"]
        after_record = after_row["record"]
        if {
            key: value for key, value in before_record.items() if key not in {"Width", "Height"}
        } != {
            key: value for key, value in after_record.items() if key not in {"Width", "Height"}
        }:
            return False
        for field, setting in (
            ("Width", "timelineResolutionWidth"),
            ("Height", "timelineResolutionHeight"),
        ):
            if field not in before_record or field not in after_record:
                return False
            if setting not in before_settings or setting not in after_settings:
                return False
            if str(before_record[field]) != str(before_settings[setting]):
                return False
            if str(after_record[field]) != str(after_settings[setting]):
                return False
    return True


def load_project_preset(project: Any, name: str) -> dict[str, Any]:
    preset_name = requested_project_preset_name(name)
    before = project_preset_records(project)
    target = _unique(before, preset_name)
    before_settings = _settings(project)
    setter = preset_method(project, "load")
    if not callable(setter):
        raise CapabilityNegotiationFailed("DaVinci Resolve project preset load is unavailable.")
    if setter(target["record"]) is not True:
        raise APICallFailed("DaVinci Resolve rejected the project preset load.")
    after_settings = _settings(project)
    after = project_preset_records(project)
    if not _catalog_preserved_after_load(before, after, before_settings, after_settings):
        raise APICallFailed("Project preset load unexpectedly changed the preset catalog.")
    for key, field in (("timelineResolutionWidth", "Width"), ("timelineResolutionHeight", "Height")):
        expected = target["record"].get(field)
        if expected is not None and str(after_settings.get(key)) != str(expected):
            raise APICallFailed("Project preset load did not match documented settings readback.")
    return {"presetName": preset_name, "loaded": True, "settingsChanged": after_settings != before_settings}


def save_project_preset(project: Any, name: str) -> dict[str, Any]:
    preset_name = requested_project_preset_name(name)
    before = project_preset_records(project)
    if preset_name in {item["name"] for item in before}:
        raise ValidationError("Project preset already exists; choose a new name.")
    unavailable = []
    for method in SAVE_METHODS:
        saver = getattr(project, method, None)
        if not callable(saver):
            unavailable.append(method)
            continue
        try:
            result = saver(preset_name)
        except APICallFailed as exc:
            detail_text = " ".join(str(value) for value in (exc.details or {}).values())
            if "method not available" in f"{exc} {detail_text}".lower():
                unavailable.append(method)
                continue
            raise
        if result is not True:
            raise APICallFailed("DaVinci Resolve did not confirm the project preset save.")
        break
    else:
        raise CapabilityNegotiationFailed(
            "Required runtime API method not available.",
            details={"capability_id": "project.preset_save", "required_method": list(SAVE_METHODS), "runtime_object": "project", "unavailable_methods": unavailable},
        )
    if _single_insertion(before, project_preset_records(project)) != preset_name:
        raise APICallFailed("DaVinci Resolve project preset save did not match exact readback.")
    return {"presetName": preset_name, "saved": True}


def _regular_input(value: str) -> tuple[Path, bytes]:
    if not isinstance(value, str) or not value or len(value) > 4096 or "\x00" in value:
        raise ValidationError("Project preset import requires a bounded file path.")
    path = Path(os.path.abspath(Path(value).expanduser()))
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise APICallFailed("Project preset import file could not be opened safely.") from exc
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        if not stat.S_ISREG(opened.st_mode) or not 0 < opened.st_size <= _MAX_BYTES:
            raise APICallFailed("Project preset import requires one bounded regular file.")
        data = source.read(_MAX_BYTES + 1)
        closed = os.fstat(source.fileno())
    if len(data) != opened.st_size or not os.path.samestat(opened, closed):
        raise APICallFailed("Project preset import file changed while reading it.")
    return path, data


def _import_state(project: Any, before: list[dict[str, Any]], settings: dict[str, Any], requested: str) -> dict[str, Any]:
    try:
        after = project_preset_records(project)
        after_settings = _settings(project)
    except Exception:
        return {"state_changed": None, "added_preset_name": None, "settings_changed": None}
    added = _single_insertion(before, after)
    return {"state_changed": after != before or after_settings != settings, "added_preset_name": added if added == requested else None, "settings_changed": after_settings != settings}


def import_project_preset(project: Any, path: str, name: str) -> dict[str, Any]:
    preset_name = requested_project_preset_name(name)
    source_path, source_bytes = _regular_input(path)
    before = project_preset_records(project)
    before_settings = _settings(project)
    if preset_name in {item["name"] for item in before}:
        raise ValidationError("Project preset import target already exists.")
    importer = getattr(project, "ImportProjectSettingsPreset", None)
    if not callable(importer):
        raise CapabilityNegotiationFailed("DaVinci Resolve project preset import is unavailable.")
    with tempfile.TemporaryDirectory(prefix=".cutagent-project-preset-import-") as folder:
        controlled = Path(folder) / source_path.name
        controlled.write_bytes(source_bytes)
        controlled.chmod(0o600)
        try:
            result = importer(str(controlled), preset_name)
        except Exception as exc:
            raise APICallFailed("DaVinci Resolve project preset import failed with uncertain state.", details=_import_state(project, before, before_settings, preset_name)) from exc
    state = _import_state(project, before, before_settings, preset_name)
    if result is not True or state["added_preset_name"] != preset_name or state["settings_changed"]:
        raise APICallFailed("DaVinci Resolve project preset import did not match exact readback.", details=state)
    return {"presetName": preset_name, "imported": True, "path": str(source_path), "sourceSha256": hashlib.sha256(source_bytes).hexdigest()}


def _read_file(path: Path, label: str) -> tuple[os.stat_result, bytes]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise APICallFailed(f"DaVinci Resolve did not create a safe {label}.") from exc
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        if not stat.S_ISREG(opened.st_mode) or not 0 < opened.st_size <= _MAX_BYTES:
            raise APICallFailed(f"DaVinci Resolve created an invalid {label}.")
        data = source.read(_MAX_BYTES + 1)
        closed = os.fstat(source.fileno())
    if len(data) != opened.st_size or not os.path.samestat(opened, closed):
        raise APICallFailed(f"DaVinci Resolve {label} changed while reading it.")
    return opened, data


def _install(source: Path, target: Path) -> os.stat_result:
    try:
        os.link(source, target)
        return os.lstat(target)
    except FileExistsError as exc:
        raise APICallFailed("Project preset export target was created concurrently.") from exc
    except OSError:
        descriptor = None
        owned = None
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            owned = os.fstat(descriptor)
            with source.open("rb") as input_file, os.fdopen(descriptor, "wb") as output_file:
                descriptor = None
                shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
                output_file.flush()
                os.fsync(output_file.fileno())
            return owned
        except FileExistsError as exc:
            raise APICallFailed("Project preset export target was created concurrently.") from exc
        except OSError as exc:
            try:
                current = os.lstat(target)
            except OSError:
                current = None
            if owned is not None and current is not None and os.path.samestat(owned, current):
                target.unlink(missing_ok=True)
            raise APICallFailed("Project preset export could not be installed safely.") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)


def _native_export(project: Any, name: str, path: Path) -> tuple[os.stat_result, bytes]:
    exporter = getattr(project, "ExportProjectSettingsPreset", None)
    if not callable(exporter):
        raise CapabilityNegotiationFailed("DaVinci Resolve project preset export is unavailable.")
    if exporter(name, str(path)) is not True:
        raise APICallFailed("DaVinci Resolve rejected the project preset export.")
    return _read_file(path, "project preset export")


def export_project_preset(project: Any, name: str, path: str) -> dict[str, Any]:
    preset_name = requested_project_preset_name(name)
    if not isinstance(path, str) or not path or len(path) > 4096 or "\x00" in path:
        raise ValidationError("Project preset export requires a bounded file path.")
    requested = Path(path).expanduser()
    try:
        parent = requested.parent.resolve(strict=True)
    except OSError as exc:
        raise APICallFailed("Project preset export folder does not exist.") from exc
    target = parent / requested.name
    if not parent.is_dir() or target.exists() or target.is_symlink():
        raise ValidationError("Project preset export target must be a new file path.")
    before = project_preset_records(project)
    before_settings = _settings(project)
    _unique(before, preset_name)
    with tempfile.TemporaryDirectory(prefix=".cutagent-project-preset-", dir=parent) as folder:
        staging = Path(folder) / target.name
        _, data = _native_export(project, preset_name, staging)
        installed = _install(staging, target)
    if project_preset_records(project) != before or _settings(project) != before_settings:
        raise APICallFailed("Project preset export unexpectedly changed project state.")
    current, installed_data = _read_file(target, "project preset export target")
    if not os.path.samestat(installed, current) or installed_data != data:
        raise APICallFailed("Project preset export target identity changed after installation.")
    return {"presetName": preset_name, "path": str(target), "exported": True, "sizeBytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _recover_delete(project: Any, name: str, backup: Path, identity: os.stat_result, data: bytes, expected: list[dict[str, Any]], settings: dict[str, Any]) -> bool:
    try:
        current = project_preset_records(project)
        current_settings = _settings(project)
        if current == expected and current_settings == settings:
            return True
        without = [item for item in expected if item["name"] != name]
        if current != without or current_settings != settings:
            return False
        checked_identity, checked_data = _read_file(backup, "project preset recovery backup")
        if not os.path.samestat(identity, checked_identity) or checked_data != data:
            return False
        importer = getattr(project, "ImportProjectSettingsPreset", None)
        if not callable(importer) or importer(str(backup), name) is not True:
            return False
        return project_preset_records(project) == expected and _settings(project) == settings
    except Exception:
        return False


def delete_project_preset(project: Any, name: str) -> dict[str, Any]:
    preset_name = requested_project_preset_name(name)
    before = project_preset_records(project)
    before_settings = _settings(project)
    _unique(before, preset_name)
    with tempfile.TemporaryDirectory(prefix=".cutagent-project-preset-delete-") as folder:
        backup = Path(folder) / "preset-backup"
        identity, data = _native_export(project, preset_name, backup)
        if project_preset_records(project) != before or _settings(project) != before_settings:
            raise APICallFailed("Project preset backup unexpectedly changed project state.")
        deleter = preset_method(project, "delete")
        if not callable(deleter):
            raise CapabilityNegotiationFailed("DaVinci Resolve project preset deletion is unavailable.")
        try:
            result = deleter(preset_name)
        except Exception as exc:
            restored = _recover_delete(project, preset_name, backup, identity, data, before, before_settings)
            raise APICallFailed("DaVinci Resolve project preset deletion failed with uncertain state.", details={"preset_name": preset_name, "preset_restored": restored}) from exc
        expected = [item for item in before if item["name"] != preset_name]
        try:
            exact = project_preset_records(project) == expected and _settings(project) == before_settings
        except Exception:
            exact = False
        if result is not True or not exact:
            restored = _recover_delete(project, preset_name, backup, identity, data, before, before_settings)
            raise APICallFailed("DaVinci Resolve project preset deletion did not match exact readback.", details={"preset_name": preset_name, "preset_restored": restored})
    return {"presetName": preset_name, "deleted": True}
