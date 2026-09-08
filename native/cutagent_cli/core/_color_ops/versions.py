from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Optional

from ...errors import APICallFailed, ValidationError


def list_color_versions(conn, clip_name: Optional[str], *, ops_module) -> list[Dict[str, str]]:
    with ops_module._with_required_page(conn, "color"):
        item = ops_module.resolve_item(conn, clip_name)
        rows = []
        for vtype, label in ((0, "local"), (1, "remote")):
            try:
                versions = item.GetVersionNameList(vtype)
                if versions:
                    for version_name in versions:
                        rows.append({"name": version_name, "type": label})
            except Exception:
                pass
        return rows


def add_color_version(conn, clip_name: Optional[str], name: str, remote: bool = False, *, ops_module) -> bool:
    with ops_module._with_required_page(conn, "color"):
        item = ops_module.resolve_item(conn, clip_name)
        vtype = 1 if remote else 0
        result = item.AddVersion(name, vtype)
        if result:
            return True
        raise APICallFailed(
            f"Failed to add version '{name}'.",
            details={"clip": clip_name, "name": name, "remote": remote, "version_type": vtype},
        )


def load_color_version(conn, clip_name: Optional[str], name: str, remote: bool = False, *, ops_module) -> Dict[str, Any]:
    with ops_module._with_required_page(conn, "color"):
        item = ops_module.resolve_item(conn, clip_name)
        vtype = 1 if remote else 0
        version_type = "remote" if remote else "local"
        available_before: Optional[list[str]] = None
        available_after: Optional[list[str]] = None
        current_before_name, current_before_type = ops_module._current_color_version(item)
        try:
            available_before = ops_module._get_color_version_names(item, vtype)
        except APICallFailed:
            available_before = None
        result = item.LoadVersionByName(name, vtype)
        if result:
            current_after_name, current_after_type = ops_module._current_color_version(item)
            try:
                available_after = ops_module._get_color_version_names(item, vtype)
            except APICallFailed:
                available_after = None
            active_after_load: Optional[bool] = None
            if current_after_name is not None:
                active_after_load = current_after_name == name and (
                    current_after_type is None or current_after_type == vtype
                )
                if not active_after_load:
                    raise APICallFailed(
                        "Color version load did not verify as active.",
                        details={
                            "clip": clip_name,
                            "name": name,
                            "remote": remote,
                            "version_type": vtype,
                            "current_after_load": current_after_name,
                            "current_after_type": current_after_type,
                        },
                    )
            return {
                "clip": clip_name,
                "name": name,
                "remote": remote,
                "version_type": version_type,
                "version_type_id": vtype,
                "loaded": True,
                "active_after_load": active_after_load,
                "current_before_load": current_before_name,
                "current_before_type_id": current_before_type,
                "current_after_load": current_after_name,
                "current_after_type_id": current_after_type,
                "available_before": available_before,
                "available_after": available_after,
            }
        if remote and available_before is not None and name in available_before:
            db_fallback = _load_remote_color_version_via_db(
                conn,
                clip_name=clip_name,
                name=name,
                ops_module=ops_module,
            )
            verification = db_fallback.get("verification") if isinstance(db_fallback, dict) else {}
            current_after = verification.get("current_after") if isinstance(verification, dict) else {}
            return {
                "clip": clip_name,
                "name": name,
                "remote": remote,
                "version_type": version_type,
                "version_type_id": vtype,
                "loaded": True,
                "active_after_load": True,
                "current_before_load": current_before_name,
                "current_before_type_id": current_before_type,
                "current_after_load": current_after.get("versionName") if isinstance(current_after, dict) else name,
                "current_after_type_id": current_after.get("versionType") if isinstance(current_after, dict) else vtype,
                "available_before": available_before,
                "available_after": verification.get("available_after") if isinstance(verification, dict) else None,
                "route": "db_workaround_color_version_load_remote",
                "native_load_result": bool(result),
                "db_fallback": db_fallback,
            }

        details = {"clip": clip_name, "name": name, "remote": remote, "version_type": vtype}
        if available_before is not None:
            details["available_versions"] = available_before
        raise APICallFailed(
            f"Version '{name}' not found.",
            details=details,
        )


def _get_color_version_names(item, version_type: int) -> list[str]:
    if not hasattr(item, "GetVersionNameList"):
        raise APICallFailed(
            "Timeline item does not support color version listing.",
            details={"version_type": version_type, "method": "GetVersionNameList"},
        )
    try:
        versions = item.GetVersionNameList(version_type) or []
    except Exception as exc:
        raise APICallFailed(
            f"Failed to list color versions: {exc}",
            details={"version_type": version_type},
        ) from exc
    if isinstance(versions, dict):
        versions = versions.values()
    return [str(version) for version in versions if version is not None]


def _current_color_version(item) -> tuple[Optional[str], Optional[int]]:
    current_version = getattr(item, "GetCurrentVersion", None)
    if callable(current_version):
        try:
            current = current_version() or {}
        except Exception:
            current = {}
        if isinstance(current, dict):
            name = (
                current.get("versionName")
                or current.get("VersionName")
                or current.get("name")
                or current.get("Name")
            )
            version_type = (
                current.get("versionType")
                if "versionType" in current
                else current.get("VersionType", current.get("type", current.get("Type")))
            )
            try:
                version_type_int = int(version_type) if version_type is not None else None
            except (TypeError, ValueError):
                version_type_int = None
            return (str(name) if name is not None else None), version_type_int
        if isinstance(current, str):
            return current, None

    current_name = getattr(item, "GetCurrentVersionName", None)
    if callable(current_name):
        try:
            name = current_name()
        except Exception:
            name = None
        if name:
            return str(name), None

    return None, None


def _target_ref_payload(target_ref: Any) -> Dict[str, Any]:
    if is_dataclass(target_ref):
        try:
            return dict(asdict(target_ref))
        except Exception:
            pass
    payload: Dict[str, Any] = {}
    for key in ("track_type", "track_index", "name", "start", "duration", "end", "aliases"):
        if not hasattr(target_ref, key):
            continue
        try:
            value = getattr(target_ref, key)
        except Exception:
            continue
        if value is not None:
            payload[key] = value
    return payload


def _resolve_target_ref_item(fresh_conn: Any, target_ref: Any, clip_name: Optional[str], *, ops_module) -> Any:
    track_index = getattr(target_ref, "track_index", None)
    start = getattr(target_ref, "start", None)
    track_type = str(getattr(target_ref, "track_type", "video") or "video")
    if track_index is not None and start is not None:
        from .. import clip_ops

        return clip_ops.find_item_by_track_record(
            fresh_conn,
            int(track_index),
            f"{int(start)}f",
            track_type=track_type,
        )
    return ops_module.resolve_item(fresh_conn, clip_name or getattr(target_ref, "name", None))


def _load_remote_color_version_via_db(
    conn,
    *,
    clip_name: Optional[str],
    name: str,
    ops_module,
) -> Dict[str, Any]:
    from ..db_session import execute_sqlite_disk_db_mutation
    from ..db_timeline_rows import find_ti_item_row
    from ..db_timeline_selection import resolve_video_group

    target_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def writer(connection, cursor, session) -> Dict[str, Any]:
        item_row = find_ti_item_row(
            cursor,
            item=target_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        local_table_id = item_row.get("pLmVerTable")
        if not local_table_id:
            raise ValidationError(
                "Selected clip has no Color version table for remote version load fallback.",
                details={"clip": target_ref.name, "target": _target_ref_payload(target_ref)},
                recoverability="manual",
            )

        table_row = cursor.execute(
            '''
            SELECT "ListMgt::LmVersionTable_id", pRemoteTable, pActive
            FROM "ListMgt::LmVersionTable"
            WHERE "ListMgt::LmVersionTable_id" = ?
            ''',
            (local_table_id,),
        ).fetchone()
        if table_row is None or not table_row["pRemoteTable"]:
            raise ValidationError(
                "Selected clip has no linked Remote Grade table for remote version load fallback.",
                details={"clip": target_ref.name, "version_table_id": local_table_id},
                recoverability="manual",
            )
        remote_table_id = str(table_row["pRemoteTable"])

        target_versions = cursor.execute(
            '''
            SELECT v."ListMgt::LmVersion_id", v.Name
            FROM "ListMgt::LmVersion" v
            JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
              ON rel.DbAssociate = v."ListMgt::LmVersion_id"
            WHERE rel.DbOwner = ? AND v.Name = ?
            ORDER BY rel.DbIndex DESC, v.rowid DESC
            ''',
            (remote_table_id, name),
        ).fetchall()
        if len(target_versions) != 1:
            raise ValidationError(
                "Remote color version load fallback requires exactly one matching remote version row.",
                details={
                    "clip": target_ref.name,
                    "name": name,
                    "remote_table_id": remote_table_id,
                    "match_count": len(target_versions),
                },
                recoverability="manual",
            )

        target_version_id = str(target_versions[0]["ListMgt::LmVersion_id"])
        linked_table_rows = cursor.execute(
            '''
            SELECT "ListMgt::LmVersionTable_id"
            FROM "ListMgt::LmVersionTable"
            WHERE pRemoteTable = ?
            ''',
            (remote_table_id,),
        ).fetchall()
        linked_table_ids = [str(row["ListMgt::LmVersionTable_id"]) for row in linked_table_rows]
        table_ids = sorted(set([remote_table_id, *linked_table_ids]))
        if not table_ids:
            table_ids = [remote_table_id]
        placeholders = ", ".join("?" for _ in table_ids)
        cursor.execute(
            f'''
            UPDATE "ListMgt::LmVersionTable"
            SET pActive = ?,
                DbSavedTime = (SELECT COALESCE(MAX(DbSavedTime), 0) + 1 FROM "ListMgt::LmVersionTable")
            WHERE "ListMgt::LmVersionTable_id" IN ({placeholders})
            ''',
            (target_version_id, *table_ids),
        )
        session.steps.append("load_remote_color_version")
        return {
            "route": "db_workaround_color_version_load_remote",
            "clip": target_ref.name,
            "target": _target_ref_payload(target_ref),
            "name": name,
            "remote": True,
            "version_type": "remote",
            "version_type_id": 1,
            "local_version_table_id": str(local_table_id),
            "remote_version_table_id": remote_table_id,
            "target_version_id": target_version_id,
            "updated_version_table_ids": table_ids,
            "updated_version_table_count": len(table_ids),
        }

    def verifier(fresh_conn, mutation_result, session) -> Dict[str, Any]:
        item = _resolve_target_ref_item(fresh_conn, target_ref, clip_name, ops_module=ops_module)
        current_after_name, current_after_type = _current_color_version(item)
        try:
            available_after = _get_color_version_names(item, 1)
        except APICallFailed:
            available_after = None
        if current_after_name != name or current_after_type not in {None, 1}:
            raise APICallFailed(
                "Remote color version DB load fallback did not verify as active after project reopen.",
                details={
                    "clip": clip_name,
                    "name": name,
                    "current_after_load": current_after_name,
                    "current_after_type": current_after_type,
                },
            )
        return {
            "status": "verified",
            "method": "Project.db LmVersionTable.pActive + DaVinci Resolve reopen readback",
            "current_after": {"versionName": current_after_name, "versionType": current_after_type},
            "available_after": available_after,
        }

    return execute_sqlite_disk_db_mutation(
        conn,
        context="color version load remote db mutation",
        writer=writer,
        verifier=verifier,
        color_target_ref=target_ref,
    )


def _load_color_version_for_delete(item, name: str, version_type: int, *, reason: str) -> str:
    result = item.LoadVersionByName(name, version_type)
    if result:
        return name
    current_name, current_type = _current_color_version(item)
    if current_name == name and current_type in {None, version_type}:
        return name
    raise APICallFailed(
        f"Failed to load fallback color version '{name}' before delete.",
        details={"fallback_version": name, "version_type": version_type, "reason": reason},
    )


def delete_color_version(
    conn,
    clip_name: Optional[str],
    name: str,
    remote: bool = False,
    *,
    ops_module,
) -> Dict[str, Any]:
    with ops_module._with_required_page(conn, "color"):
        item = ops_module.resolve_item(conn, clip_name)
        vtype = 1 if remote else 0
        if not hasattr(item, "DeleteVersionByName"):
            raise APICallFailed(
                "Timeline item does not support color version deletion.",
                details={"clip": clip_name, "name": name, "remote": remote, "version_type": vtype},
            )

        before = ops_module._get_color_version_names(item, vtype)
        target_count = before.count(name)
        if target_count <= 0:
            raise ValidationError(
                f"Version '{name}' not found.",
                details={
                    "clip": clip_name,
                    "name": name,
                    "remote": remote,
                    "version_type": vtype,
                    "available_versions": before,
                },
            )

        deleted_count = 0
        loaded_fallbacks: list[str] = []
        attempts: list[Dict[str, Any]] = []

        for _ in range(target_count):
            available = ops_module._get_color_version_names(item, vtype)
            if name not in available:
                break
            fallback = next((version_name for version_name in available if version_name != name), None)
            fallback_loaded_this_attempt = False
            current_name, current_type = ops_module._current_color_version(item)
            if current_name == name and current_type in {None, vtype}:
                if not fallback:
                    raise ValidationError(
                        f"Cannot delete the active only version '{name}'.",
                        details={
                            "clip": clip_name,
                            "name": name,
                            "remote": remote,
                            "version_type": vtype,
                            "available_versions": available,
                        },
                    )
                loaded_fallbacks.append(
                    ops_module._load_color_version_for_delete(item, fallback, vtype, reason="target_is_current")
                )
                fallback_loaded_this_attempt = True

            before_attempt = ops_module._get_color_version_names(item, vtype)
            try:
                result = item.DeleteVersionByName(name, vtype)
            except Exception as exc:
                raise APICallFailed(
                    f"Failed to delete version '{name}': {exc}",
                    details={
                        "clip": clip_name,
                        "name": name,
                        "remote": remote,
                        "version_type": vtype,
                        "available_versions": before_attempt,
                        "attempts": attempts,
                    },
                ) from exc
            after_attempt = ops_module._get_color_version_names(item, vtype)
            attempts.append(
                {
                    "result": bool(result),
                    "before_count": before_attempt.count(name),
                    "after_count": after_attempt.count(name),
                }
            )
            if after_attempt.count(name) < before_attempt.count(name):
                deleted_count += before_attempt.count(name) - after_attempt.count(name)
                continue

            if fallback and not fallback_loaded_this_attempt:
                loaded_fallbacks.append(
                    ops_module._load_color_version_for_delete(item, fallback, vtype, reason="delete_noop")
                )
                retry_before = ops_module._get_color_version_names(item, vtype)
                retry_result = item.DeleteVersionByName(name, vtype)
                retry_after = ops_module._get_color_version_names(item, vtype)
                attempts.append(
                    {
                        "result": bool(retry_result),
                        "before_count": retry_before.count(name),
                        "after_count": retry_after.count(name),
                        "after_fallback": fallback,
                    }
                )
                if retry_after.count(name) < retry_before.count(name):
                    deleted_count += retry_before.count(name) - retry_after.count(name)
                    continue
                after_attempt = retry_after

            raise APICallFailed(
                f"Failed to delete version '{name}'.",
                details={
                    "clip": clip_name,
                    "name": name,
                    "remote": remote,
                    "version_type": vtype,
                    "before_versions": before_attempt,
                    "after_versions": after_attempt,
                    "attempts": attempts,
                },
            )

        after = ops_module._get_color_version_names(item, vtype)
        if name in after:
            raise APICallFailed(
                f"Failed to delete all versions named '{name}'.",
                details={
                    "clip": clip_name,
                    "name": name,
                    "remote": remote,
                    "version_type": vtype,
                    "before_versions": before,
                    "after_versions": after,
                    "deleted_count": deleted_count,
                    "attempts": attempts,
                },
            )
        return {
            "clip": clip_name,
            "name": name,
            "remote": remote,
            "version_type": vtype,
            "deleted": True,
            "deleted_count": deleted_count,
            "loaded_fallbacks": loaded_fallbacks,
            "remaining_versions": after,
        }
