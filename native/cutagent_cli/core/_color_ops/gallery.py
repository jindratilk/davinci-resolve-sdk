from __future__ import annotations

from typing import Any, Dict, Optional

from ...errors import APICallFailed
from ...policy import require_api_method
from .. import color_page_db
from .. import gallery_ops
from .. import project_ops


def list_gallery_albums(conn) -> list[Dict[str, str]]:
    return gallery_ops.list_albums(conn)


def get_current_album_info(conn) -> Dict[str, Any]:
    gallery, album = gallery_ops._resolve_album(conn, None)
    name = gallery_ops._album_name(album, "Current Album", gallery=gallery)
    rows: list[dict[str, Any]] = []
    current_index = None
    try:
        albums = gallery.GetGalleryStillAlbums() or []
    except Exception:
        albums = []
    for index, candidate in enumerate(albums, 1):
        candidate_name = gallery_ops._album_name(candidate, f"Album {index}", gallery=gallery)
        row_current = candidate is album
        if not row_current and name != "Current Album":
            row_current = str(candidate_name).strip().casefold() == str(name).strip().casefold()
        row = {"index": index, "name": candidate_name, "current": row_current}
        if row_current:
            current_index = index
            name = candidate_name
        rows.append(row)
    if current_index is None and len(rows) == 1:
        rows[0]["current"] = True
        current_index = rows[0]["index"]
        name = rows[0]["name"]
    return {
        "name": name,
        "index": current_index,
        "album_count": len(rows) if rows else None,
        "albums": rows,
        "current": True,
        "album": name,
    }


def switch_gallery_album(conn, name: str) -> bool:
    data = gallery_ops.switch_album(conn, name)
    return bool(data.get("switched"))


def list_gallery_stills(conn) -> list[Dict[str, Any]]:
    return gallery_ops.list_stills(conn)


def grab_still(conn, *, ops_module) -> bool:
    with ops_module._with_required_page(conn, "color"):
        timeline = getattr(conn, "timeline", None)
        if not timeline:
            raise APICallFailed(
                "No active timeline for still grab.",
                details={"preflight": "missing_timeline"},
            )

        current_item = None
        if hasattr(timeline, "GetCurrentVideoItem"):
            try:
                current_item = timeline.GetCurrentVideoItem()
            except Exception:
                current_item = None

        if not current_item:
            try:
                from ..clip_ops import get_current_item

                current_item = get_current_item(conn)
            except Exception:
                current_item = None

        if not current_item:
            raise APICallFailed(
                "No clip under playhead for still grab.",
                details={"preflight": "no_current_video_item"},
            )

        if not hasattr(timeline, "GrabStill"):
            raise APICallFailed(
                "GrabStill API is not available on this DaVinci Resolve timeline object.",
                details={"preflight": "missing_grabstill_method"},
            )

        try:
            result = timeline.GrabStill()
        except Exception as exc:
            raise APICallFailed(
                "GrabStill failed with an exception.",
                details={"preflight": "grabstill_exception", "exception_type": exc.__class__.__name__},
            ) from exc

        if result is False or result is None:
            raise APICallFailed(
                "GrabStill returned failure.",
                details={"preflight": "grabstill_returned_failure"},
            )
        return True


def export_still(conn, selector: str, output_path_or_dir: str, fmt: str = "drx") -> Dict[str, Any]:
    data = gallery_ops.export_still(conn, selector, output_path_or_dir, fmt=fmt)
    return {
        "selector": selector,
        "output": output_path_or_dir,
        "format": fmt.lower(),
        **({"requested_output": data.get("requested_output")} if "requested_output" in data else {}),
    }


def import_stills(conn, path: str) -> Dict[str, Any]:
    data = gallery_ops.import_stills(conn, path)
    return {"path": path, "imported": bool(data is not None)}


def _export_still_to_drx(conn, still: Any) -> str:
    _, album = gallery_ops._resolve_album(conn, None)
    return gallery_ops._export_still_to_drx(album, still)


def apply_still(
    conn,
    selector: str,
    clip_name: Optional[str] = None,
    mode: int = 0,
    album: Optional[str] = None,
    *,
    ops_module,
) -> Dict[str, Any]:
    target, stills = gallery_ops._get_stills(conn, album)
    if not stills:
        raise APICallFailed("No stills available in target album.")
    still = gallery_ops._resolve_still(target, stills, selector)
    drx = gallery_ops._export_still_to_drx(target, still)
    before_readback = color_page_db.read_color_grade_for_clip(conn, clip_name=clip_name)
    before_signature = color_page_db._grade_state_signature(before_readback)
    ops_module.apply_grade_from_file(conn, clip_name, drx, mode)
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
                "still_label": gallery_ops._still_label(target, still),
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
        "still_label": gallery_ops._still_label(target, still),
        "drx_path": drx,
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


def _get_gallery(conn):
    return gallery_ops._get_gallery(conn)


def _get_current_album(conn):
    return gallery_ops._resolve_album(conn, None)


def _resolve_still_selector(stills: list[Any], selector: str, *, target_album) -> Any:
    return gallery_ops._resolve_still(target_album, stills, selector)


def list_power_grades(conn) -> list[Dict[str, Any]]:
    rows = _power_grade_rows(conn)
    return _public_power_grade_rows(rows)


def _power_grade_rows(conn) -> list[Dict[str, Any]]:
    gallery = _get_gallery(conn)
    getter = require_api_method(
        gallery,
        "GetGalleryPowerGradeAlbums",
        capability_id="color.gallery_power_grade_list_album",
        runtime_object="gallery",
    )
    albums = gallery_ops._normalize_stills(getter() or [])
    rows: list[Dict[str, Any]] = []
    global_index = 1
    for album_index, album in enumerate(albums, 1):
        album_name = gallery_ops._album_name(album, f"Power Grade {album_index}", gallery=gallery)
        stills = album.GetStills() if hasattr(album, "GetStills") else []
        stills = gallery_ops._normalize_stills(stills or [])
        for still_idx, still in enumerate(stills, 1):
            rows.append(
                {
                    "index": global_index,
                    "album": str(album_name),
                    "album_index": album_index,
                    "label": gallery_ops._still_label(album, still),
                    "album_obj": album,
                    "still": still,
                }
            )
            global_index += 1
    return rows


def _public_power_grade_rows(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return [
        {
            "index": row["index"],
            "album": row["album"],
            "album_index": row["album_index"],
            "label": row["label"],
        }
        for row in rows
    ]


def _resolve_power_grade_row(rows: list[Dict[str, Any]], selector: str) -> Dict[str, Any]:
    if not rows:
        raise APICallFailed("No power grades available.")
    selector_text = str(selector or "").strip()
    if selector_text.isdigit():
        idx = int(selector_text)
        for row in rows:
            if row["index"] == idx:
                return row
        raise APICallFailed(
            "Power grade index out of range.",
            details={
                "selector": selector,
                "power_grade_count": len(rows),
                "available_power_grades": _public_power_grade_rows(rows),
            },
        )

    selector_key = selector_text.casefold()
    for row in rows:
        if row["label"] == selector_text:
            return row
    for row in rows:
        if str(row["label"] or "").strip().casefold() == selector_key:
            return row
    raise APICallFailed(
        f"Power grade '{selector}' not found.",
        details={
            "selector": selector,
            "power_grade_count": len(rows),
            "available_power_grades": _public_power_grade_rows(rows),
        },
    )


def apply_power_grade(
    conn,
    selector: str,
    clip_name: Optional[str] = None,
    mode: int = 0,
    *,
    ops_module,
) -> Dict[str, Any]:
    rows = _power_grade_rows(conn)
    selected = _resolve_power_grade_row(rows, selector)
    before_readback = color_page_db.read_color_grade_for_clip(conn, clip_name=clip_name)
    before_signature = color_page_db._grade_state_signature(before_readback)
    try:
        drx = gallery_ops._export_still_to_drx(
            selected["album_obj"],
            selected["still"],
            capability_id="color.power_grade_apply",
        )
    except APICallFailed as exc:
        raise APICallFailed(
            "PowerGrade still could not be exported to a DRX for verified application.",
            details={
                "selector": selector,
                "album": selected["album"],
                "album_index": selected["album_index"],
                "label": selected["label"],
                "available_power_grades": _public_power_grade_rows(rows),
                "export_error": str(exc),
                "export_error_details": exc.details,
            },
            recoverability="manual",
        ) from exc
    ops_module.apply_grade_from_file(conn, clip_name, drx, mode)
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
                "album": selected["album"],
                "album_index": selected["album_index"],
                "label": selected["label"],
                "before_signature": before_signature,
                "after_signature": after_signature,
                "after_readback": after_readback,
            },
        )
    return {
        "selector": selector,
        "clip": after_readback.get("clip") or clip_name,
        "mode": mode,
        "album": selected["album"],
        "album_index": selected["album_index"],
        "label": selected["label"],
        "drx_path": drx,
        "applied": True,
        "verified": True,
        "route": "api_native_power_grade_apply",
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
