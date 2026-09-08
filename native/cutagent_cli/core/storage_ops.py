"""Media Storage operations."""

from __future__ import annotations

import json
import hashlib
import hmac
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from ..errors import APICallFailed, CapabilityNegotiationFailed, SdkMutationStaleRevision, ValidationError
from . import media_pool
from .sdk_live_inspection import media_pool_native_id, require_media_pool_mutation_guard


SDK_STORAGE_ARTIFACT_GUARD_ENV = "CUTAGENT_SDK_STORAGE_ARTIFACT_GUARD"
SDK_STORAGE_ARTIFACT_DIGESTS_ENV = "CUTAGENT_SDK_STORAGE_ARTIFACT_DIGESTS"
SDK_STORAGE_ARTIFACT_GUARD_DIGEST_ENV = "CUTAGENT_SDK_STORAGE_ARTIFACT_GUARD_DIGEST"
SDK_EXPECTED_STORAGE_FOLDER_TARGET_ENV = "CUTAGENT_SDK_EXPECTED_STORAGE_FOLDER_TARGET"
SDK_STORAGE_RECEIPT_PATH_ENV = "CUTAGENT_SDK_STORAGE_RECEIPT_PATH"
SDK_STORAGE_RECEIPT_NONCE_ENV = "CUTAGENT_SDK_STORAGE_RECEIPT_NONCE"


def _fsync_parent_directory(parent: Path) -> None:
    """Persist a directory entry where the host exposes POSIX directory handles."""
    if sys.platform == "win32":
        return
    directory = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _write_storage_receipt(kind: str, data: dict[str, Any]) -> None:
    receipt_path = os.environ.get(SDK_STORAGE_RECEIPT_PATH_ENV)
    if receipt_path is None:
        return
    nonce = os.environ.get(SDK_STORAGE_RECEIPT_NONCE_ENV)
    if not nonce:
        raise SdkMutationStaleRevision("Managed Storage execution receipt identity is unavailable.")
    target = Path(receipt_path)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    payload = {"kind": kind, "nonce": nonce, "data": data}
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    os.replace(temporary, target)
    _fsync_parent_directory(target.parent)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _same_native_identity(path: Path, expected: dict[str, Any], *, directory: bool) -> bool:
    stat = path.lstat()
    return (not path.is_symlink()
            and (path.is_dir() if directory else path.is_file())
            and stat.st_dev == expected.get("device")
            and stat.st_ino == expected.get("inode"))


def _verify_guarded_directory(record: dict[str, Any]) -> None:
    root = Path(record["path"])
    if not _same_native_identity(root, record["identity"], directory=True):
        raise SdkMutationStaleRevision("Managed Storage directory identity changed after authorization.")
    expected_directories = {entry["relativePath"]: entry for entry in record.get("directoryEntries", [])}
    expected_files = {entry["relativePath"]: entry for entry in record.get("entries", [])}
    manifest = {"directoryEntries": record.get("directoryEntries", []), "entries": record.get("entries", [])}
    calculated_tree_digest = f"sha256:{hashlib.sha256(json.dumps(manifest, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()}"
    if calculated_tree_digest != record.get("treeDigest"):
        raise SdkMutationStaleRevision("Managed Storage directory guard digest is invalid.")
    actual_directories: set[str] = set()
    actual_files: set[str] = set()
    for current, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        files.sort()
        current_path = Path(current)
        for name in directories:
            child = current_path / name
            relative = child.relative_to(root).as_posix()
            actual_directories.add(relative)
            expected = expected_directories.get(relative)
            if expected is None or not _same_native_identity(child, expected["identity"], directory=True):
                raise SdkMutationStaleRevision("Managed Storage directory changed after authorization.")
        for name in files:
            child = current_path / name
            relative = child.relative_to(root).as_posix()
            actual_files.add(relative)
            expected = expected_files.get(relative)
            if expected is None or not _same_native_identity(child, expected["identity"], directory=False) or _sha256_file(child) != expected.get("sha256"):
                raise SdkMutationStaleRevision("Managed Storage directory content changed after authorization.")
    if actual_directories != set(expected_directories) or actual_files != set(expected_files):
        raise SdkMutationStaleRevision("Managed Storage directory hierarchy changed after authorization.")


def _require_storage_artifact_guard(paths: list[str]) -> None:
    guard_path = os.environ.get(SDK_STORAGE_ARTIFACT_GUARD_ENV)
    if guard_path is None:
        return
    try:
        payload = json.loads(Path(guard_path).read_text(encoding="utf-8"))
        records = payload["artifacts"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SdkMutationStaleRevision("Managed Storage artifact guard is unavailable after authorization.") from exc
    if not isinstance(records, list) or not records:
        raise SdkMutationStaleRevision("Managed Storage artifact guard is invalid.")
    calculated_guard_digest = f"sha256:{hashlib.sha256(json.dumps(records, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()}"
    if not hmac.compare_digest(calculated_guard_digest, os.environ.get(SDK_STORAGE_ARTIFACT_GUARD_DIGEST_ENV, "")):
        raise SdkMutationStaleRevision("Managed Storage artifact guard changed after authorization.")
    try:
        expected_digests = json.loads(os.environ[SDK_STORAGE_ARTIFACT_DIGESTS_ENV])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SdkMutationStaleRevision("Authorized managed Storage artifact digests are unavailable.") from exc
    record_digests = [record.get("treeDigest") or record.get("sha256") for record in records if isinstance(record, dict)]
    if (not isinstance(expected_digests, list) or not expected_digests
            or record_digests != expected_digests):
        raise SdkMutationStaleRevision("Managed Storage artifact guard does not match the authorized payload digests.")
    guarded_roots: list[Path] = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str) or not isinstance(record.get("identity"), dict):
            raise SdkMutationStaleRevision("Managed Storage artifact guard is invalid.")
        guarded = Path(record["path"])
        guarded_roots.append(guarded)
        if record.get("kind") == "directory":
            _verify_guarded_directory(record)
        elif record.get("kind") == "file":
            if not _same_native_identity(guarded, record["identity"], directory=False) or _sha256_file(guarded) != record.get("sha256"):
                raise SdkMutationStaleRevision("Managed Storage artifact changed after authorization.")
        else:
            raise SdkMutationStaleRevision("Managed Storage artifact guard is invalid.")
    for raw_path in paths:
        candidate = Path(raw_path)
        if not any(candidate == root or root in candidate.parents for root in guarded_roots):
            raise SdkMutationStaleRevision("Storage execution path is outside the authorized managed artifact guard.")


def _media_storage(conn):
    resolve = getattr(conn, "resolve", None)
    getter = getattr(resolve, "GetMediaStorage", None)
    if not callable(getter):
        raise APICallFailed("Cannot access Media Storage.")
    storage = getter()
    if not storage:
        raise APICallFailed("Cannot access Media Storage.")
    return storage


def reveal_in_storage(conn, path: str) -> dict[str, Any]:
    """Reveal a path in DaVinci Resolve's Media Storage panel."""
    _require_storage_artifact_guard([path])
    storage = _media_storage(conn)
    revealer = getattr(storage, "RevealInStorage", None)
    if not callable(revealer):
        raise CapabilityNegotiationFailed(
            "MediaStorage.RevealInStorage is not available.",
            details={"capability_id": "storage.reveal", "required_method": "MediaStorage.RevealInStorage"},
        )
    result = revealer(path)
    if result is False:
        raise APICallFailed("Failed to reveal path in Media Storage.", details={"path": path})
    data = {"path": path, "revealed": bool(result)}
    _write_storage_receipt("reveal", data)
    return data


def import_from_storage(conn, path_or_options: Any) -> dict[str, Any]:
    """Import path(s) or DaVinci Resolve import-option dictionaries into the Media Pool."""
    if isinstance(path_or_options, dict):
        guarded_paths = [path_or_options.get("media")]
    elif isinstance(path_or_options, list) and path_or_options and isinstance(path_or_options[0], dict):
        guarded_paths = [value.get("media") for value in path_or_options]
    else:
        guarded_paths = list(path_or_options) if isinstance(path_or_options, list) else [path_or_options]
    _require_storage_artifact_guard([value for value in guarded_paths if isinstance(value, str)])
    require_media_pool_mutation_guard(conn)
    storage = _media_storage(conn)
    importer = getattr(storage, "AddItemListToMediaPool", None)
    if not callable(importer):
        raise CapabilityNegotiationFailed(
            "MediaStorage.AddItemListToMediaPool is not available.",
            details={"capability_id": "storage.import", "required_method": "MediaStorage.AddItemListToMediaPool"},
        )
    payload = path_or_options if isinstance(path_or_options, list) else [path_or_options]
    items = importer(payload)
    if not items:
        raise APICallFailed("Failed to import from storage.", details={"payload": payload})
    native_ids = [media_pool_native_id(item) for item in items]
    if any(not value for value in native_ids):
        raise CapabilityNegotiationFailed("Imported Media Pool identity readback is unavailable.", details={"capability_id": "storage.import"})
    data = {"imported_count": len(items), "items": [item.GetName() if hasattr(item, "GetName") else str(item) for item in items], "native_ids": native_ids}
    if not isinstance(path_or_options, dict) and not (isinstance(path_or_options, list) and path_or_options and isinstance(path_or_options[0], dict)):
        _write_storage_receipt("import", {**data, "path": guarded_paths[0]})
    return data


def import_subclip(conn, path: str, start_frame: int, end_frame: int) -> dict[str, Any]:
    """Import a source subclip using DaVinci Resolve's dict import surface."""
    if end_frame <= start_frame:
        raise ValidationError(
            "Subclip end-frame must be greater than start-frame.",
            details={"start_frame": start_frame, "end_frame": end_frame},
        )
    options = {"media": path, "startFrame": int(start_frame), "endFrame": int(end_frame)}
    data = import_from_storage(conn, options)
    data.update({"path": path, "start_frame": int(start_frame), "end_frame": int(end_frame)})
    _write_storage_receipt("import_subclip", data)
    return data


def import_sequence(conn, pattern: str, start_index: Optional[int] = None, end_index: Optional[int] = None) -> dict[str, Any]:
    """Import an image sequence using DaVinci Resolve's dict import surface."""
    if start_index is not None and end_index is not None and end_index < start_index:
        raise ValidationError(
            "Sequence end-index must be greater than or equal to start-index.",
            details={"start_index": start_index, "end_index": end_index},
        )
    _require_storage_artifact_guard([pattern])
    require_media_pool_mutation_guard(conn)
    importer = getattr(conn.media_pool, "ImportMedia", None)
    if not callable(importer):
        raise CapabilityNegotiationFailed(
            "MediaPool.ImportMedia is not available for image sequence import.",
            details={"capability_id": "media.import", "required_method": "MediaPool.ImportMedia"},
        )
    options: dict[str, Any] = {"FilePath": pattern}
    if start_index is not None:
        options["StartIndex"] = int(start_index)
    if end_index is not None:
        options["EndIndex"] = int(end_index)
    items = importer([options])
    if not items:
        raise APICallFailed("Failed to import image sequence.", details={"options": options})
    native_ids = [media_pool_native_id(item) for item in items]
    if any(not value for value in native_ids):
        raise CapabilityNegotiationFailed("Imported sequence identity readback is unavailable.", details={"capability_id": "storage.import_sequence"})
    data = {"imported_count": len(items), "items": [item.GetName() if hasattr(item, "GetName") else str(item) for item in items], "native_ids": native_ids}
    data.update({"pattern": pattern, "start_index": start_index, "end_index": end_index})
    _write_storage_receipt("import_sequence", data)
    return data


def add_clip_mattes(conn, clip_name: str, paths: list[str], eye: Optional[str] = None) -> dict[str, Any]:
    """Add matte files to a Media Pool clip."""
    _require_storage_artifact_guard(paths)
    if not paths:
        raise ValidationError("At least one matte path is required.", details={"paths": paths})
    clip = media_pool.find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    expected_target = os.environ.get("CUTAGENT_SDK_EXPECTED_STORAGE_MEDIA_TARGET")
    if expected_target is not None:
        try:
            target = json.loads(expected_target)
        except json.JSONDecodeError as exc:
            raise ValidationError("SDK Storage media target is malformed.") from exc
        if target != {"nativeId": media_pool_native_id(clip), "name": clip_name}:
            raise SdkMutationStaleRevision("The exact Media Pool matte target changed before execution.")
    require_media_pool_mutation_guard(conn)
    storage = _media_storage(conn)
    method = getattr(storage, "AddClipMattesToMediaPool", None)
    if not callable(method):
        raise CapabilityNegotiationFailed(
            "Clip matte import is not available through this DaVinci Resolve scripting API.",
            details={"capability_id": "storage.matte.add", "required_method": "MediaStorage.AddClipMattesToMediaPool"},
        )
    if eye:
        result = method(clip, paths, eye)
    else:
        result = method(clip, paths)
    if result is False:
        raise APICallFailed("Failed to add clip matte(s).", details={"clip": clip_name, "paths": paths, "eye": eye})
    getter = getattr(conn.media_pool, "GetClipMatteList", None)
    if not callable(getter):
        raise CapabilityNegotiationFailed("Clip matte association readback is unavailable.", details={"capability_id": "storage.matte.add"})
    attached = getter(clip) or []
    attached_paths = attached if isinstance(attached, list) else [attached]
    if not all(path in attached_paths for path in paths):
        raise APICallFailed("Clip matte association did not match authoritative readback.", details={"clip": clip_name})
    data = {"clip": clip_name, "paths": paths, "eye": eye, "added": bool(result), "verified_paths": paths}
    _write_storage_receipt("matte.add", data)
    return data


def _media_pool_item_names(items: Any) -> list[str]:
    names: list[str] = []
    for item in items or []:
        getter = getattr(item, "GetName", None)
        if callable(getter):
            try:
                names.append(str(getter()))
                continue
            except Exception:
                pass
        names.append(str(item))
    return names


def add_timeline_mattes(conn, paths: list[str]) -> dict[str, Any]:
    """Add timeline matte files to the Media Pool in the current process."""
    _require_storage_artifact_guard(paths)
    if not paths:
        raise ValidationError("At least one matte path is required.", details={"paths": paths})
    require_media_pool_mutation_guard(conn)
    current_folder = conn.media_pool.GetCurrentFolder()
    expected_folder = os.environ.get(SDK_EXPECTED_STORAGE_FOLDER_TARGET_ENV)
    if expected_folder is not None and (current_folder is None or media_pool_native_id(current_folder, folder=True) != expected_folder):
        raise SdkMutationStaleRevision("The current Media Pool folder changed after Storage authorization.")
    storage = _media_storage(conn)
    method = getattr(storage, "AddTimelineMattesToMediaPool", None)
    if not callable(method):
        raise CapabilityNegotiationFailed(
            "Timeline matte import is not available through this DaVinci Resolve scripting API.",
            details={"capability_id": "storage.matte.timeline_add", "required_method": "MediaStorage.AddTimelineMattesToMediaPool"},
        )
    result = method(paths)
    if result is False or result is None:
        raise APICallFailed("Failed to add timeline matte(s).", details={"paths": paths})
    item_names = _media_pool_item_names(result)
    current_folder = conn.media_pool.GetCurrentFolder()
    getter = getattr(conn.media_pool, "GetTimelineMatteList", None)
    if not current_folder or not callable(getter):
        raise CapabilityNegotiationFailed("Timeline matte association readback is unavailable.", details={"capability_id": "storage.matte.timeline_add"})
    attached = getter(current_folder) or []
    attached_paths = attached if isinstance(attached, list) else [attached]
    if not all(path in attached_paths for path in paths):
        raise APICallFailed("Timeline matte association did not match authoritative readback.")
    data = {
        "paths": paths,
        "added": bool(result),
        "created_count": len(result) if isinstance(result, list) else int(bool(result)),
        "items": item_names,
        "verified_paths": paths,
    }
    _write_storage_receipt("matte.timeline_add", data)
    return data


def add_timeline_mattes_isolated(paths: list[str], *, timeout: float = 30.0) -> dict[str, Any]:
    """Add timeline mattes in a worker process so native proxy teardown crashes are caught.

    DaVinci Resolve 21 beta can return a successful ``[MediaPoolItems]`` result and then
    crash the Python process while cleaning up native scripting proxy objects.
    Running the native call in a short-lived worker lets the public CLI report a
    deterministic API failure instead of emitting ``ok: true`` followed by
    ``SIGSEGV``.
    """
    if not paths:
        raise ValidationError("At least one matte path is required.", details={"paths": paths})

    with tempfile.TemporaryDirectory(prefix="cutagent-cli-timeline-matte-") as tmp:
        status_path = Path(tmp) / "status.json"
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cutagent_cli._timeline_matte_worker",
                    str(status_path),
                    json.dumps(paths),
                ],
                cwd=str(Path(__file__).resolve().parents[2]),
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise APICallFailed(
                "Timeline matte import worker timed out.",
                details={"timeout_seconds": timeout},
            ) from exc
        status: dict[str, Any] | None = None
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text())
            except json.JSONDecodeError:
                status = None

        if proc.returncode != 0:
            raise APICallFailed(
                "Timeline matte import worker exited unexpectedly.",
                details={
                    "paths": paths,
                    "worker_exit_code": proc.returncode,
                    "worker_status": status,
                    "stdout": proc.stdout[-2000:],
                    "stderr": proc.stderr[-2000:],
                },
            )

        if not status:
            raise APICallFailed(
                "Timeline matte import worker did not return a status payload.",
                details={"paths": paths, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]},
            )

        if not status.get("ok"):
            error = status.get("error") if isinstance(status.get("error"), dict) else {}
            raise APICallFailed(
                error.get("message") or "Failed to add timeline matte(s).",
                details=error.get("details") if isinstance(error.get("details"), dict) else {"paths": paths},
            )

        data = status.get("data")
        if not isinstance(data, dict):
            raise APICallFailed("Timeline matte import worker returned malformed data.", details={"paths": paths, "status": status})
        return data
