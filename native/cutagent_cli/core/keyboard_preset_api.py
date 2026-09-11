"""Strict DaVinci Resolve 21.1 keyboard-preset operations."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

from ..errors import APICallFailed, ValidationError


def _keyboard_preset_method(connection: Any, name: str):
    resolve = getattr(connection, "resolve", None)
    method = getattr(resolve, name, None)
    if not callable(method):
        raise APICallFailed(f"DaVinci Resolve {name} is unavailable.")
    return method


def _preset_name(value: Any, *, method: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 1024
        or "\x00" in value
    ):
        raise APICallFailed(
            f"DaVinci Resolve {method} returned an invalid keyboard preset name."
        )
    return value


def requested_preset_name(value: Any) -> str:
    """Validate one exact opaque preset name without trimming or aliasing it."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 1024
        or "\x00" in value
    ):
        raise ValidationError("Keyboard preset name must be a bounded nonempty string.")
    return value


def list_keyboard_presets(connection: Any) -> list[str]:
    """Return the exact ordered keyboard-preset catalog from DaVinci Resolve."""
    raw = _keyboard_preset_method(connection, "GetKeyboardPresetList")()
    if not isinstance(raw, list):
        raise APICallFailed(
            "DaVinci Resolve GetKeyboardPresetList returned an invalid keyboard preset list."
        )
    return [_preset_name(value, method="GetKeyboardPresetList") for value in raw]


def get_current_keyboard_preset(connection: Any) -> str:
    """Return the exact active keyboard-preset name from DaVinci Resolve."""
    raw = _keyboard_preset_method(connection, "GetCurrentKeyboardPreset")()
    return _preset_name(raw, method="GetCurrentKeyboardPreset")


def _require_unique_catalog_name(catalog: list[str], name: str) -> None:
    matches = sum(value == name for value in catalog)
    if matches != 1:
        raise APICallFailed(
            "DaVinci Resolve keyboard preset target is missing or ambiguous.",
            details={"preset_name": name, "matching_entries": matches},
        )


def load_keyboard_preset(connection: Any, name: str) -> dict[str, Any]:
    preset_name = requested_preset_name(name)
    before_catalog = list_keyboard_presets(connection)
    _require_unique_catalog_name(before_catalog, preset_name)
    before_current = get_current_keyboard_preset(connection)
    if before_current == preset_name:
        return {
            "presetName": preset_name,
            "previousPresetName": before_current,
            "changed": False,
        }
    result = _keyboard_preset_method(connection, "LoadKeyboardPreset")(preset_name)
    if result is not True:
        raise APICallFailed("DaVinci Resolve rejected the keyboard preset load.")
    try:
        after_catalog = list_keyboard_presets(connection)
        after_current = get_current_keyboard_preset(connection)
    except Exception as exc:
        restored = _restore_loaded_preset(connection, before_current, before_catalog)
        raise APICallFailed(
            "DaVinci Resolve keyboard preset load readback failed.",
            details={"preset_name": preset_name, "previous_preset_restored": restored},
        ) from exc
    if after_catalog != before_catalog or after_current != preset_name:
        restored = _restore_loaded_preset(connection, before_current, before_catalog)
        raise APICallFailed(
            "DaVinci Resolve keyboard preset load did not match exact readback.",
            details={
                "preset_name": preset_name,
                "current_preset": after_current,
                "previous_preset_restored": restored,
            },
        )
    return {
        "presetName": preset_name,
        "previousPresetName": before_current,
        "changed": True,
    }


def _restore_loaded_preset(
    connection: Any, previous_name: str, expected_catalog: list[str]
) -> bool:
    try:
        restore = _keyboard_preset_method(connection, "LoadKeyboardPreset")(previous_name)
        return bool(
            restore is True
            and list_keyboard_presets(connection) == expected_catalog
            and get_current_keyboard_preset(connection) == previous_name
        )
    except Exception:
        return False


def delete_keyboard_preset(connection: Any, name: str) -> dict[str, Any]:
    preset_name = requested_preset_name(name)
    before_catalog = list_keyboard_presets(connection)
    _require_unique_catalog_name(before_catalog, preset_name)
    before_current = get_current_keyboard_preset(connection)
    if before_current == preset_name:
        raise ValidationError("The active keyboard preset cannot be deleted.")
    with tempfile.TemporaryDirectory(prefix=".cutagent-keyboard-delete-") as folder:
        backup_path = Path(folder) / "preset-backup"
        backup_identity, backup_sha256 = _export_keyboard_preset_backup(
            connection, preset_name, backup_path
        )
        if (
            list_keyboard_presets(connection) != before_catalog
            or get_current_keyboard_preset(connection) != before_current
        ):
            raise APICallFailed(
                "Keyboard preset backup unexpectedly changed preset state."
            )
        try:
            result = _keyboard_preset_method(connection, "DeleteKeyboardPreset")(preset_name)
        except Exception as exc:
            restored = _recover_deleted_keyboard_preset(
                connection, preset_name, backup_path, backup_identity,
                backup_sha256, before_catalog, before_current
            )
            raise APICallFailed(
                "DaVinci Resolve keyboard preset deletion failed with uncertain state.",
                details={"preset_name": preset_name, "preset_restored": restored},
            ) from exc
        expected_catalog = [value for value in before_catalog if value != preset_name]
        try:
            after_catalog = list_keyboard_presets(connection)
            after_current = get_current_keyboard_preset(connection)
        except Exception as exc:
            restored = _recover_deleted_keyboard_preset(
                connection, preset_name, backup_path, backup_identity,
                backup_sha256, before_catalog, before_current
            )
            raise APICallFailed(
                "DaVinci Resolve keyboard preset deletion readback failed.",
                details={"preset_name": preset_name, "preset_restored": restored},
            ) from exc
        if result is not True or after_catalog != expected_catalog or after_current != before_current:
            restored = _recover_deleted_keyboard_preset(
                connection, preset_name, backup_path, backup_identity,
                backup_sha256, before_catalog, before_current
            )
            raise APICallFailed(
                "DaVinci Resolve keyboard preset deletion did not match exact readback.",
                details={"preset_name": preset_name, "preset_restored": restored},
            )
    return {"presetName": preset_name, "deleted": True}


def _export_keyboard_preset_backup(
    connection: Any, name: str, path: Path
) -> tuple[os.stat_result, str]:
    result = _keyboard_preset_method(connection, "ExportKeyboardPreset")(name, str(path))
    if result is not True:
        raise APICallFailed("DaVinci Resolve did not confirm the keyboard preset backup.")
    return _bounded_file_identity(path, "keyboard preset backup")


def _bounded_file_identity(path: Path, label: str) -> tuple[os.stat_result, str]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise APICallFailed(f"DaVinci Resolve did not create a safe {label}.") from exc
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        if not stat.S_ISREG(opened.st_mode) or opened.st_size < 1 or opened.st_size > 16 * 1024 * 1024:
            raise APICallFailed(f"DaVinci Resolve created an invalid {label}.")
        data = source.read(16 * 1024 * 1024 + 1)
        closed = os.fstat(source.fileno())
    if len(data) != opened.st_size or not os.path.samestat(opened, closed):
        raise APICallFailed(f"DaVinci Resolve {label} changed while reading it.")
    return opened, hashlib.sha256(data).hexdigest()


def _recover_deleted_keyboard_preset(
    connection: Any,
    name: str,
    backup_path: Path,
    backup_identity: os.stat_result,
    backup_sha256: str,
    expected_catalog: list[str],
    expected_current: str,
) -> bool:
    """Restore only an exact missing target; ambiguous state requires manual recovery."""
    try:
        current_catalog = list_keyboard_presets(connection)
        current = get_current_keyboard_preset(connection)
        if current_catalog == expected_catalog and current == expected_current:
            return True
        expected_without_target = [value for value in expected_catalog if value != name]
        if current_catalog != expected_without_target or current != expected_current:
            return False
        current_identity, current_sha256 = _bounded_file_identity(
            backup_path, "keyboard preset backup"
        )
        if (
            not os.path.samestat(backup_identity, current_identity)
            or current_sha256 != backup_sha256
        ):
            return False
        imported = _keyboard_preset_method(connection, "ImportKeyboardPreset")(
            str(backup_path), name
        )
        if imported is not True:
            return False
        if get_current_keyboard_preset(connection) != expected_current:
            if _keyboard_preset_method(connection, "LoadKeyboardPreset")(expected_current) is not True:
                return False
        return (
            list_keyboard_presets(connection) == expected_catalog
            and get_current_keyboard_preset(connection) == expected_current
        )
    except Exception:
        return False


def _regular_import_file(value: str) -> tuple[Path, bytes]:
    if not isinstance(value, str) or not value or len(value) > 4096 or "\x00" in value:
        raise ValidationError("Keyboard preset import requires a bounded file path.")
    path = Path(os.path.abspath(Path(value).expanduser()))
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise APICallFailed("Keyboard preset import file could not be opened safely.") from exc
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        if not stat.S_ISREG(opened.st_mode) or opened.st_size < 1 or opened.st_size > 16 * 1024 * 1024:
            raise APICallFailed("Keyboard preset import requires one bounded regular file.")
        data = source.read(16 * 1024 * 1024 + 1)
        closed = os.fstat(source.fileno())
    if len(data) != opened.st_size or len(data) > 16 * 1024 * 1024 or not os.path.samestat(opened, closed):
        raise APICallFailed("Keyboard preset import file changed while reading it.")
    return path, data


def import_keyboard_preset(
    connection: Any, path: str, name: str | None = None
) -> dict[str, Any]:
    import_path, source_bytes = _regular_import_file(path)
    preset_name = requested_preset_name(name) if name is not None else None
    before_catalog = list_keyboard_presets(connection)
    before_current = get_current_keyboard_preset(connection)
    if preset_name is not None and preset_name in before_catalog:
        raise ValidationError("Keyboard preset import target already exists.")
    importer = _keyboard_preset_method(connection, "ImportKeyboardPreset")
    with tempfile.TemporaryDirectory(prefix=".cutagent-keyboard-import-") as folder:
        controlled_path = Path(folder) / import_path.name
        controlled_path.write_bytes(source_bytes)
        controlled_path.chmod(0o600)
        try:
            result = importer(str(controlled_path), preset_name) if preset_name is not None else importer(str(controlled_path))
        except Exception as exc:
            state = _keyboard_import_state(connection, before_catalog, before_current, preset_name)
            raise APICallFailed(
                "DaVinci Resolve keyboard preset import failed with uncertain state.",
                details=state,
            ) from exc
    state = _keyboard_import_state(connection, before_catalog, before_current, preset_name)
    added_name = state.get("added_preset_name")
    if result is not True or not isinstance(added_name, str):
        raise APICallFailed(
            "DaVinci Resolve keyboard preset import did not create exactly one requested preset.",
            details=state,
        )
    activated = state["current_preset"] != before_current
    if activated:
        restored = _restore_loaded_preset(connection, before_current, state["catalog"])
        if not restored:
            raise APICallFailed(
                "DaVinci Resolve activated the imported keyboard preset and the previous preset could not be restored.",
                details={**state, "previous_preset_restored": False},
            )
    final_catalog = list_keyboard_presets(connection)
    final_current = get_current_keyboard_preset(connection)
    if final_catalog != state["catalog"] or final_current != before_current:
        raise APICallFailed(
            "DaVinci Resolve keyboard preset import final state did not match exact readback.",
            details={
                **state,
                "previous_preset_restored": final_current == before_current,
                "final_catalog": final_catalog,
                "final_current_preset": final_current,
            },
        )
    return {
        "presetName": added_name,
        "imported": True,
        "path": str(import_path),
        "activatedByImport": activated,
        "previousPresetRestored": True,
    }


def _keyboard_import_state(
    connection: Any,
    before_catalog: list[str],
    before_current: str,
    requested_name: str | None,
) -> dict[str, Any]:
    """Describe exact post-import state without claiming uncertain cleanup."""
    try:
        catalog = list_keyboard_presets(connection)
        current = get_current_keyboard_preset(connection)
    except Exception:
        return {
            "state_changed": None,
            "added_preset_name": None,
            "current_preset": None,
            "catalog": None,
        }
    candidates = [
        catalog[index]
        for index in range(len(catalog))
        if catalog[:index] + catalog[index + 1 :] == before_catalog
    ] if len(catalog) == len(before_catalog) + 1 else []
    distinct = set(candidates)
    added_name = next(iter(distinct)) if len(distinct) == 1 else None
    if added_name in before_catalog or (
        requested_name is not None and added_name != requested_name
    ):
        added_name = None
    return {
        "state_changed": catalog != before_catalog or current != before_current,
        "added_preset_name": added_name,
        "current_preset": current,
        "catalog": catalog,
    }


def _install_new_file(source: Path, target: Path) -> os.stat_result:
    try:
        os.link(source, target)
        return os.lstat(target)
    except FileExistsError as exc:
        raise APICallFailed("Keyboard preset export target was created concurrently.") from exc
    except OSError:
        descriptor: int | None = None
        owned_stat: os.stat_result | None = None
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            owned_stat = os.fstat(descriptor)
            with source.open("rb") as input_file, os.fdopen(descriptor, "wb") as output_file:
                descriptor = None
                shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
                output_file.flush()
                os.fsync(output_file.fileno())
            return owned_stat
        except FileExistsError as exc:
            raise APICallFailed("Keyboard preset export target was created concurrently.") from exc
        except OSError as exc:
            try:
                current = os.lstat(target)
            except OSError:
                current = None
            if owned_stat is not None and current is not None and os.path.samestat(owned_stat, current):
                target.unlink(missing_ok=True)
            raise APICallFailed("Keyboard preset export could not be installed safely.") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)


def export_keyboard_preset(connection: Any, name: str, path: str) -> dict[str, Any]:
    preset_name = requested_preset_name(name)
    if not isinstance(path, str) or not path or len(path) > 4096 or "\x00" in path:
        raise ValidationError("Keyboard preset export requires a bounded file path.")
    requested = Path(path).expanduser()
    try:
        parent = requested.parent.resolve(strict=True)
    except OSError as exc:
        raise APICallFailed("Keyboard preset export folder does not exist.") from exc
    target = parent / requested.name
    if not parent.is_dir() or target.exists() or target.is_symlink():
        raise ValidationError("Keyboard preset export target must be a new file path.")
    before_catalog = list_keyboard_presets(connection)
    before_current = get_current_keyboard_preset(connection)
    _require_unique_catalog_name(before_catalog, preset_name)
    with tempfile.TemporaryDirectory(prefix=".cutagent-keyboard-preset-", dir=parent) as folder:
        staging = Path(folder) / target.name
        result = _keyboard_preset_method(connection, "ExportKeyboardPreset")(
            preset_name, str(staging)
        )
        if result is not True:
            raise APICallFailed("DaVinci Resolve rejected the keyboard preset export.")
        try:
            metadata = staging.lstat()
        except OSError as exc:
            raise APICallFailed("DaVinci Resolve did not create the keyboard preset export.") from exc
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size < 1 or metadata.st_size > 16 * 1024 * 1024:
            raise APICallFailed("DaVinci Resolve created an invalid keyboard preset export.")
        installed = _install_new_file(staging, target)
    if list_keyboard_presets(connection) != before_catalog or get_current_keyboard_preset(connection) != before_current:
        raise APICallFailed("Keyboard preset export unexpectedly changed preset state.")
    try:
        current = os.lstat(target)
    except OSError as exc:
        raise APICallFailed("Keyboard preset export target disappeared after installation.") from exc
    if not os.path.samestat(installed, current) or not stat.S_ISREG(current.st_mode):
        raise APICallFailed("Keyboard preset export target identity changed after installation.")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise APICallFailed("Keyboard preset export target could not be opened safely.") from exc
    with os.fdopen(descriptor, "rb") as output_file:
        opened = os.fstat(output_file.fileno())
        if not os.path.samestat(installed, opened):
            raise APICallFailed("Keyboard preset export target changed while opening it.")
        data = output_file.read(16 * 1024 * 1024 + 1)
        closed = os.fstat(output_file.fileno())
    if len(data) != current.st_size or len(data) > 16 * 1024 * 1024 or not os.path.samestat(installed, closed):
        raise APICallFailed("Keyboard preset export target changed while reading it.")
    return {
        "presetName": preset_name,
        "path": str(target),
        "exported": True,
        "sizeBytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
