"""Gallery still album and still operations."""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Optional, List, Dict, Any

from ..errors import APICallFailed
from ..policy import require_api_method


def _get_gallery(conn):
    getter = require_api_method(
        conn.project,
        "GetGallery",
        capability_id="color.gallery_stills",
        runtime_object="project",
    )
    gallery = getter()
    if not gallery:
        raise APICallFailed("Failed to access project gallery.")
    return gallery


def _album_name(album, default_name: str, gallery=None) -> str:
    if gallery is not None:
        getter = getattr(gallery, "GetAlbumName", None)
        if callable(getter):
            try:
                name = getter(album)
                if name:
                    return str(name)
            except Exception:
                pass
    if hasattr(album, "GetName"):
        try:
            name = album.GetName()
            if name:
                return str(name)
        except Exception:
            pass
    if hasattr(album, "GetLabel"):
        for arg in ("", None):
            try:
                name = album.GetLabel(arg)
                if name:
                    return str(name)
            except TypeError:
                continue
            except Exception:
                break
        try:
            name = album.GetLabel()
            if name:
                return str(name)
        except Exception:
            pass
    for attr in ("Name", "name", "Label", "label"):
        name = getattr(album, attr, None)
        if name:
            return str(name)
    return default_name


def _album_key(name: str) -> str:
    return str(name or "").strip().casefold()


def _get_albums(conn):
    gallery = _get_gallery(conn)
    getter = require_api_method(
        gallery,
        "GetGalleryStillAlbums",
        capability_id="color.gallery_stills",
        runtime_object="gallery",
    )
    albums = getter() or []
    return gallery, albums


def _resolve_album(conn, album: Optional[str] = None):
    gallery, albums = _get_albums(conn)
    if album is None:
        getter = require_api_method(
            gallery,
            "GetCurrentStillAlbum",
            capability_id="color.gallery_stills",
            runtime_object="gallery",
        )
        current = getter()
        if not current:
            raise APICallFailed("No current still album is selected.")
        return gallery, current

    if album.isdigit():
        idx = int(album)
        if 1 <= idx <= len(albums):
            return gallery, albums[idx - 1]
        raise APICallFailed(
            "Album index out of range.",
            details={"album": album, "album_count": len(albums)},
        )

    requested_key = _album_key(album)
    for i, current in enumerate(albums, 1):
        if _album_name(current, f"Album {i}", gallery=gallery) == album:
            return gallery, current
    for i, current in enumerate(albums, 1):
        if _album_key(_album_name(current, f"Album {i}", gallery=gallery)) == requested_key:
            return gallery, current

    raise APICallFailed(
        f"Album '{album}' not found.",
        details={
            "album": album,
            "available_albums": [_album_name(current, f"Album {i}", gallery=gallery) for i, current in enumerate(albums, 1)],
        },
    )


def _same_album(left, right, gallery=None) -> bool:
    if left is right:
        return True
    if left is None or right is None:
        return False
    left_name = _album_name(left, "", gallery=gallery)
    right_name = _album_name(right, "", gallery=gallery)
    return bool(left_name and right_name and _album_key(left_name) == _album_key(right_name))


def list_albums(conn) -> List[Dict[str, Any]]:
    """List gallery still albums."""
    gallery, albums = _get_albums(conn)
    rows = []
    for i, album in enumerate(albums, 1):
        rows.append({"index": i, "name": _album_name(album, f"Album {i}", gallery=gallery)})
    return rows


def create_album(conn, album_name: Optional[str] = None) -> Dict[str, Any]:
    """Create a gallery still album."""
    gallery = _get_gallery(conn)
    before_albums = []
    try:
        before_albums = list(gallery.GetGalleryStillAlbums() or [])
    except Exception:
        before_albums = []
    creator = require_api_method(
        gallery,
        "CreateGalleryStillAlbum",
        capability_id="color.gallery_stills",
        runtime_object="gallery",
    )
    try:
        album = creator(album_name) if album_name else creator()
    except TypeError:
        album = creator()
    if not album:
        raise APICallFailed("Failed to create gallery still album.", details={"album_name": album_name})
    renamed = False
    if album_name:
        setter = getattr(gallery, "SetAlbumName", None)
        if callable(setter):
            renamed = bool(setter(album, album_name))
    after_albums = []
    try:
        after_albums = list(gallery.GetGalleryStillAlbums() or [])
    except Exception:
        after_albums = []
    created_index = None
    created_album = None
    for index, candidate in enumerate(after_albums, 1):
        if candidate is album:
            created_index = index
            created_album = candidate
            break
    if created_album is None and len(after_albums) > len(before_albums):
        created_index = len(after_albums)
        created_album = after_albums[-1]

    readback_name = _album_name(created_album or album, album_name or "Untitled", gallery=gallery)
    if created_album is None:
        raise APICallFailed(
            "Created gallery album but it was not returned by album list readback.",
            details={
                "requested_name": album_name,
                "readback_name": readback_name,
                "renamed": renamed,
                "before_count": len(before_albums),
                "after_count": len(after_albums),
                "available_albums": [
                    _album_name(candidate, f"Album {idx}", gallery=gallery) for idx, candidate in enumerate(after_albums, 1)
                ],
            },
        )
    name_verified = True
    if album_name:
        name_verified = _album_key(readback_name) == _album_key(album_name)
        if not name_verified:
            raise APICallFailed(
                "Created gallery album but requested name did not verify.",
                details={
                    "requested_name": album_name,
                    "readback_name": readback_name,
                    "renamed": renamed,
                    "before_count": len(before_albums),
                    "after_count": len(after_albums),
                    "available_albums": [
                        _album_name(candidate, f"Album {idx}", gallery=gallery) for idx, candidate in enumerate(after_albums, 1)
                    ],
                },
            )
    data = {
        "name": readback_name,
        "requested_name": album_name,
        "created": True,
        "verified": bool(created_album is not None),
        "name_verified": name_verified,
        "index": created_index,
        "before_count": len(before_albums),
        "after_count": len(after_albums),
    }
    if renamed:
        data["renamed"] = True
    return data


def create_power_grade_album(conn, album_name: str) -> Dict[str, Any]:
    """Create a PowerGrade album and name it with DaVinci Resolve's gallery API."""
    gallery = _get_gallery(conn)
    creator = require_api_method(
        gallery,
        "CreateGalleryPowerGradeAlbum",
        capability_id="color.gallery_power_grade_list_album",
        runtime_object="gallery",
    )
    album = creator()
    if not album:
        raise APICallFailed("Failed to create PowerGrade album.", details={"album_name": album_name})
    setter = getattr(gallery, "SetAlbumName", None)
    renamed = bool(setter(album, album_name)) if callable(setter) else False
    return {"name": _album_name(album, album_name, gallery=gallery), "renamed": renamed, "power_grade": True}


def rename_album(conn, album: str, new_name: str) -> Dict[str, Any]:
    """Rename a gallery still album through DaVinci Resolve's gallery API."""
    gallery, target = _resolve_album(conn, album)
    old_name = _album_name(target, str(album), gallery=gallery)
    setter = require_api_method(
        gallery,
        "SetAlbumName",
        capability_id="color.gallery_stills",
        runtime_object="gallery",
    )
    result = setter(target, new_name)
    if result is False:
        raise APICallFailed("Failed to rename gallery album.", details={"album": album, "new_name": new_name})
    return {"old_name": old_name, "name": _album_name(target, new_name, gallery=gallery), "renamed": bool(result), "api_method": "SetAlbumName"}


def switch_album(conn, album: str) -> Dict[str, Any]:
    """Switch current still album by 1-based index or name."""
    gallery, target = _resolve_album(conn, album)
    setter = require_api_method(
        gallery,
        "SetCurrentStillAlbum",
        capability_id="color.gallery_stills",
        runtime_object="gallery",
    )
    target_name = _album_name(target, str(album), gallery=gallery)
    result = setter(target)
    current = None
    try:
        current_getter = getattr(gallery, "GetCurrentStillAlbum", None)
        if callable(current_getter):
            current = current_getter()
    except Exception:
        current = None
    verified = _same_album(current, target, gallery=gallery)
    if result is not False or verified:
        return {
            "album": target_name,
            "requested_album": album,
            "switched": True,
            "verified": verified,
        }
    raise APICallFailed(
        "Failed to switch gallery album.",
        details={"album": album, "resolved_album": target_name, "verified": verified},
    )


def _get_stills(conn, album: Optional[str] = None):
    _, target = _resolve_album(conn, album)
    getter = require_api_method(
        target,
        "GetStills",
        capability_id="color.gallery_stills",
        runtime_object="gallery_album",
    )
    stills = _normalize_stills(getter() or [])
    return target, stills


def _normalize_stills(stills: Any) -> List[Any]:
    if isinstance(stills, dict):
        return list(stills.values())
    if isinstance(stills, list):
        return stills
    if isinstance(stills, tuple):
        return list(stills)
    try:
        return list(stills)
    except TypeError:
        return []


def _still_label(target_album, still: Any) -> str:
    try:
        label = target_album.GetLabel(still)
        if label:
            return str(label)
    except Exception:
        pass
    if hasattr(still, "GetLabel"):
        for arg in ("", None):
            try:
                label = still.GetLabel(arg)
                if label:
                    return str(label)
            except TypeError:
                continue
            except Exception:
                break
        try:
            label = still.GetLabel()
            if label:
                return str(label)
        except Exception:
            pass
    for attr in ("Label", "label", "Name", "name"):
        label = getattr(still, attr, None)
        if label:
            return str(label)
    return ""


def _still_rows(target_album, stills: List[Any]) -> List[Dict[str, Any]]:
    return [{"index": i, "label": _still_label(target_album, still)} for i, still in enumerate(stills, 1)]


def _resolve_still(target_album, stills: List[Any], selector: str):
    selector_text = str(selector or "").strip()
    if selector_text.isdigit():
        idx = int(selector_text)
        if 1 <= idx <= len(stills):
            return stills[idx - 1]
        raise APICallFailed(
            "Still index out of range.",
            details={"selector": selector, "still_count": len(stills), "available_stills": _still_rows(target_album, stills)},
        )

    selector_key = _album_key(selector_text)
    for still in stills:
        if _still_label(target_album, still) == selector_text:
            return still
    for still in stills:
        if _album_key(_still_label(target_album, still)) == selector_key:
            return still

    raise APICallFailed(
        f"Still '{selector}' not found.",
        details={"selector": selector, "still_count": len(stills), "available_stills": _still_rows(target_album, stills)},
    )


def list_stills(conn, album: Optional[str] = None) -> List[Dict[str, Any]]:
    """List stills in an album (or current album)."""
    target, stills = _get_stills(conn, album)
    return _still_rows(target, stills)


def import_stills(conn, path: str, album: Optional[str] = None) -> Dict[str, Any]:
    """Import still image(s) to album."""
    target, _ = _get_stills(conn, album)
    importer = require_api_method(
        target,
        "ImportStills",
        capability_id="color.gallery_stills",
        runtime_object="gallery_album",
    )
    result = None
    try:
        result = importer(path)
    except TypeError:
        result = importer([path])
    if result is False:
        raise APICallFailed("ImportStills failed.", details={"path": path, "album": album})
    return {"path": path, "album": album or "current"}


def export_still(
    conn,
    selector: str,
    output_path_or_dir: str,
    fmt: str = "drx",
    album: Optional[str] = None,
) -> Dict[str, Any]:
    """Export one still from album."""
    target, stills = _get_stills(conn, album)
    if not stills:
        raise APICallFailed("No stills available in target album.")
    still = _resolve_still(target, stills, selector)

    exporter = require_api_method(
        target,
        "ExportStills",
        capability_id="color.gallery_stills",
        runtime_object="gallery_album",
    )
    fmt_upper = fmt.upper()
    out_path = os.path.abspath(output_path_or_dir)
    out_dir = out_path if os.path.isdir(out_path) else os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    prefix = os.path.splitext(os.path.basename(out_path))[0] if not os.path.isdir(out_path) else ""

    attempted_signatures = _export_stills_native_variants(exporter, [still], out_dir, prefix, fmt_upper)
    result = any(attempt.get("success") for attempt in attempted_signatures)

    if not result:
        raise APICallFailed(
            "ExportStills failed.",
            details={
                "selector": selector,
                "still_label": _still_label(target, still),
                "output": output_path_or_dir,
                "format": fmt,
                "attempted_signatures": attempted_signatures,
                "available_stills": _still_rows(target, stills),
            },
        )
    output = _normalize_exported_still_path(out_path, out_dir, prefix, fmt_upper)
    return {
        "selector": selector,
        "output": output,
        "requested_output": output_path_or_dir,
        "format": fmt.lower(),
        "album": album or "current",
        "still_label": _still_label(target, still),
    }


def _export_stills_native_variants(exporter, stills: List[Any], out_dir: str, prefix: str, fmt_upper: str) -> List[Dict[str, Any]]:
    variants = [
        ("stills,out_dir,prefix,fmt", (stills, out_dir, prefix, fmt_upper)),
        ("stills,out_dir,prefix,fmt_lower", (stills, out_dir, prefix, fmt_upper.lower())),
        ("stills,out_dir,fmt", (stills, out_dir, fmt_upper)),
        ("stills,out_dir", (stills, out_dir)),
    ]
    attempts: List[Dict[str, Any]] = []
    for label, args in variants:
        attempt: Dict[str, Any] = {"signature": label}
        try:
            call_result = exporter(*args)
        except TypeError as exc:
            attempt["exception"] = exc.__class__.__name__
            attempts.append(attempt)
            continue
        except Exception as exc:
            attempt["exception"] = exc.__class__.__name__
            attempts.append(attempt)
            continue
        attempt["result"] = bool(call_result)
        attempt["success"] = call_result is not False
        attempts.append(attempt)
        if call_result is not False:
            break
    return attempts


def _normalize_exported_still_path(out_path: str, out_dir: str, prefix: str, fmt_upper: str) -> str:
    if os.path.isdir(out_path):
        return out_path
    if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
        return out_path

    extension = f".{fmt_upper.lower()}"
    candidates: List[str] = []
    try:
        names = os.listdir(out_dir)
    except Exception:
        names = []
    for file_name in names:
        lower = file_name.lower()
        if not lower.endswith(extension):
            continue
        if prefix and not os.path.splitext(file_name)[0].startswith(prefix):
            continue
        candidate = os.path.join(out_dir, file_name)
        if os.path.abspath(candidate) != out_path and os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
            candidates.append(candidate)
    if not candidates:
        for file_name in names:
            candidate = os.path.join(out_dir, file_name)
            if (file_name.lower().endswith(extension)
                    and os.path.abspath(candidate) != out_path
                    and os.path.isfile(candidate)
                    and os.path.getsize(candidate) > 0):
                candidates.append(candidate)

    if candidates:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        candidate = candidates[0]
        if os.path.isfile(out_path):
            with open(candidate, "rb") as source, open(out_path, "r+b") as destination:
                destination.seek(0)
                destination.truncate(0)
                shutil.copyfileobj(source, destination, length=1024 * 1024)
                destination.flush()
                os.fsync(destination.fileno())
            os.unlink(candidate)
        else:
            shutil.move(candidate, out_path)
        return out_path

    raise APICallFailed(
        "Exported still but expected output file was not found.",
        details={"requested_output": out_path, "export_dir": out_dir, "format": fmt_upper.lower()},
    )


def _export_still_to_drx(target_album, still: Any, *, capability_id: str = "color.gallery_stills") -> str:
    exporter = require_api_method(
        target_album,
        "ExportStills",
        capability_id=capability_id,
        runtime_object="gallery_album",
    )
    tmpdir = tempfile.mkdtemp(prefix="resolve_still_")
    attempts = _export_stills_native_variants(exporter, [still], tmpdir, "", "DRX")
    result = any(attempt.get("success") for attempt in attempts)

    if not result:
        raise APICallFailed(
            "Failed to export still to DRX.",
            details={"still_label": _still_label(target_album, still), "attempted_signatures": attempts},
        )
    for file_name in os.listdir(tmpdir):
        if file_name.lower().endswith(".drx"):
            return os.path.join(tmpdir, file_name)
    raise APICallFailed(
        "Exported still but no DRX file found.",
        details={"still_label": _still_label(target_album, still), "export_dir": tmpdir},
    )


def delete_still(conn, selector: str, album: Optional[str] = None) -> bool:
    """Delete one still from album."""
    target, stills = _get_stills(conn, album)
    if not stills:
        raise APICallFailed("No stills available in target album.")
    still = _resolve_still(target, stills, selector)
    still_label = _still_label(target, still)
    deleter = require_api_method(
        target,
        "DeleteStills",
        capability_id="color.gallery_stills",
        runtime_object="gallery_album",
    )
    before = _still_rows(target, stills)
    try:
        result = deleter([still])
    except TypeError:
        result = deleter(still)
    if result is False:
        raise APICallFailed(
            "DeleteStills failed.",
            details={"selector": selector, "album": album, "still_label": still_label, "available_stills": before},
        )
    after_stills = _normalize_stills(getattr(target, "GetStills", lambda: [])() or [])
    if any(candidate is still for candidate in after_stills):
        raise APICallFailed(
            "DeleteStills returned success but still remains in album.",
            details={
                "selector": selector,
                "album": album,
                "still_label": still_label,
                "before_stills": before,
                "after_stills": _still_rows(target, after_stills),
            },
        )
    return True


def get_still_label(conn, selector: str, album: Optional[str] = None) -> Dict[str, Any]:
    """Get still label."""
    target, stills = _get_stills(conn, album)
    if not stills:
        raise APICallFailed("No stills available in target album.")
    still = _resolve_still(target, stills, selector)
    getter = require_api_method(
        target,
        "GetLabel",
        capability_id="color.gallery_stills",
        runtime_object="gallery_album",
    )
    label = getter(still)
    return {"selector": selector, "label": str(label or ""), "album": album or "current"}


def apply_still(
    conn,
    selector: str,
    clip_name: Optional[str] = None,
    mode: int = 0,
    album: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply a gallery still grade to a clip via DRX export/import."""
    target, stills = _get_stills(conn, album)
    if not stills:
        raise APICallFailed("No stills available in target album.")
    still = _resolve_still(target, stills, selector)

    from . import color_ops

    from . import color_page_db

    before_readback = color_page_db.read_color_grade_for_clip(conn, clip_name=clip_name)
    before_signature = color_page_db._grade_state_signature(before_readback)
    drx_path = _export_still_to_drx(target, still)
    color_ops.apply_grade_from_file(conn, clip_name, drx_path, mode)
    from . import project_ops

    project_ops.save_current_project_if_available(conn)
    after_readback = color_page_db.read_color_grade_for_clip(conn, clip_name=clip_name)
    after_signature = color_page_db._grade_state_signature(after_readback)
    if not after_signature["has_grade"] or after_signature["raw_param_count"] <= 0:
        raise APICallFailed(
            "ApplyGradeFromDRX returned success but Color Page grade readback did not verify.",
            details={
                "selector": selector,
                "clip": clip_name,
                "mode": mode,
                "album": album or "current",
                "still_label": _still_label(target, still),
                "before_signature": before_signature,
                "after_signature": after_signature,
                "after_readback": after_readback,
            },
        )
    return {
        "selector": selector,
        "clip": after_readback.get("clip") or clip_name,
        "mode": mode,
        "album": album or "current",
        "still_label": _still_label(target, still),
        "drx_path": drx_path,
        "applied": True,
        "verified": True,
        "route": "api_native_gallery_still_apply",
        "verification": {
            "status": "verified",
            "route": "db_readback_after_api_apply",
            "clip": after_readback.get("clip"),
            "clip_id": after_readback.get("clip_id"),
            "changed": after_signature["sha256"] != before_signature["sha256"],
            "before_signature_sha256": before_signature["sha256"],
            "after_signature_sha256": after_signature["sha256"],
            "has_grade": after_signature["has_grade"],
            "raw_param_count": after_signature["raw_param_count"],
        },
    }


def set_still_label(conn, selector: str, label: str, album: Optional[str] = None) -> bool:
    """Set still label."""
    target, stills = _get_stills(conn, album)
    if not stills:
        raise APICallFailed("No stills available in target album.")
    still = _resolve_still(target, stills, selector)
    setter = require_api_method(
        target,
        "SetLabel",
        capability_id="color.gallery_stills",
        runtime_object="gallery_album",
    )
    result = setter(still, label)
    if result:
        return True
    raise APICallFailed(
        "Failed to set still label.",
        details={"selector": selector, "label": label, "album": album},
    )
