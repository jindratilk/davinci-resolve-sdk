"""PowerGrade library access and verified DB-backed grade application.

PowerGrade albums live in the per-user gallery database (`User.db`, sibling of
the per-user `Projects/` folder). Each PowerGrade still is a `Gallery::GyStill`
row referenced by a `Gallery::GyStillRef` (Type=1) and links the full grade
body through `pClipFullVer`/`pClipVer` into the user-level
`ListMgt::LmVersion.Body` — the same compressed VersionBody protobuf the
project-level Color Page DB routes already read and write.

Live DaVinci Resolve Studio 21 proof (2026-06-10): a wheel+HDR graded clip was
grabbed into "PowerGrade 1"; the User.db LmVersion body parsed with the
existing codec and contained the full grade. Native
`GalleryStillAlbum.ExportStills` returned False for every format in the same
session, so the DRX-based API route stays unavailable and application goes
through the verified Disk Project.db close/write/reopen machinery instead.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from ..errors import APICallFailed, ValidationError
from .db_session import DiskDbMutationSession, execute_sqlite_disk_db_mutation
from .db_timeline_rows import find_ti_item_row
from .color_page_db import (
    compress_version_body,
    decompress_version_body,
    read_color_grade,
)


def user_gallery_db_path_from_project_db(project_db_path: str) -> str:
    """Derive the per-user User.db path from a Disk Project.db path."""
    # .../Users/<user>/Projects/<project>/Project.db -> .../Users/<user>/User.db
    project_dir = os.path.dirname(os.path.abspath(project_db_path))
    projects_dir = os.path.dirname(project_dir)
    user_dir = os.path.dirname(projects_dir)
    candidate = os.path.join(user_dir, "User.db")
    if os.path.basename(projects_dir) != "Projects" or not os.path.isfile(candidate):
        raise APICallFailed(
            "Could not locate the per-user gallery database (User.db) next to the project database.",
            details={"project_db_path": project_db_path, "candidate": candidate},
            recoverability="manual",
        )
    return candidate


def list_power_grade_stills(user_db_path: str) -> list[dict[str, Any]]:
    """List PowerGrade stills stored in the per-user gallery database."""
    connection = sqlite3.connect(user_db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            '''
            SELECT ref."Gallery::GyStillRef_id" AS ref_id,
                   ref.CreateTime AS ref_create_time,
                   still."Gallery::GyStill_id" AS still_id,
                   still.Label AS label,
                   still.CreateTime AS create_time,
                   still.pClipFullVer AS full_ver,
                   still.pClipVer AS clip_ver
            FROM "Gallery::GyStillRef" ref
            JOIN "Gallery::GyStill" still
              ON still."Gallery::GyStill_id" = ref.Ref0
            WHERE ref.Type = 1
            ORDER BY still.CreateTime, still.rowid
            ''',
        ).fetchall()
    finally:
        connection.close()
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        out.append(
            {
                "index": index,
                "label": row["label"],
                "still_id": row["still_id"],
                "created": row["create_time"],
                "version_id": row["full_ver"] or row["clip_ver"],
            }
        )
    return out


def _resolve_power_grade_row(rows: list[dict[str, Any]], selector: str) -> dict[str, Any]:
    if not rows:
        raise APICallFailed(
            "No PowerGrade stills found in the user gallery database.",
            details={"hint": "Grab a still into a PowerGrade album first."},
            recoverability="not_applicable",
        )
    text = str(selector or "").strip()
    if text.isdigit():
        for row in rows:
            if row["index"] == int(text):
                return row
        raise ValidationError(
            "PowerGrade index out of range.",
            details={"selector": selector, "available": [
                {"index": r["index"], "label": r["label"]} for r in rows
            ]},
            recoverability="not_applicable",
        )
    folded = text.casefold()
    for row in rows:
        if str(row["label"] or "") == text:
            return row
    for row in rows:
        if str(row["label"] or "").strip().casefold() == folded:
            return row
    raise ValidationError(
        f"PowerGrade '{selector}' not found.",
        details={"selector": selector, "available": [
            {"index": r["index"], "label": r["label"]} for r in rows
        ]},
        recoverability="not_applicable",
    )


def read_power_grade_body(user_db_path: str, version_id: str) -> bytes:
    connection = sqlite3.connect(user_db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            'SELECT Body FROM "ListMgt::LmVersion" WHERE "ListMgt::LmVersion_id" = ?',
            (version_id,),
        ).fetchone()
    finally:
        connection.close()
    if not row or not row["Body"]:
        raise APICallFailed(
            "PowerGrade still does not reference a grade body in the user gallery database.",
            details={"version_id": version_id, "user_db_path": user_db_path},
            recoverability="manual",
        )
    return bytes(row["Body"])


def _float_param_signature(params) -> list[tuple[int, str, float]]:
    out = []
    for param in params:
        if isinstance(param.value, float):
            out.append((param.node_index, f"0x{param.key:08X}", round(param.value, 5)))
        elif isinstance(param.value, int):
            out.append((param.node_index, f"0x{param.key:08X}", float(param.value)))
    out.sort()
    return out


def apply_power_grade_db(
    conn: Any,
    *,
    selector: str,
    clip_name: str | None = None,
) -> dict[str, Any]:
    """Apply a PowerGrade still's grade body to a timeline clip via Project.db."""
    from ..runtime_health import resolve_current_disk_project_db
    from .db_timeline_selection import resolve_video_group
    from .color_page_db import (
        _create_lm_version_table_for_item,
        _insert_lm_version_from_body,
        _parse_params_from_proto,
        _VERSION_TABLE_FIELDS_BLOB_HEX,
    )
    import uuid as _uuid

    current_database = resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    project_db_path = str(current_database.get("project_db_path") or "")
    user_db_path = user_gallery_db_path_from_project_db(project_db_path)
    rows = list_power_grade_stills(user_db_path)
    selected = _resolve_power_grade_row(rows, selector)
    if not selected.get("version_id"):
        raise APICallFailed(
            "Selected PowerGrade still does not link a grade version.",
            details={"selected": selected},
            recoverability="manual",
        )
    source_blob = read_power_grade_body(user_db_path, str(selected["version_id"]))
    source_proto = decompress_version_body(source_blob)
    source_params = _parse_params_from_proto(source_proto)
    if not source_params:
        raise APICallFailed(
            "PowerGrade grade body parsed to zero parameters; refusing to apply.",
            details={"selected": selected},
            recoverability="manual",
        )
    expected_signature = _float_param_signature(source_params)

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        ver = None
        if ver_table_id:
            ver = cursor.execute(
                '''SELECT v."ListMgt::LmVersion_id", v.Body
                   FROM "ListMgt::LmVersion" v
                   JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
                     ON rel.DbAssociate = v."ListMgt::LmVersion_id"
                   WHERE rel.DbOwner = ? AND v.HasCorrection = 1
                   ORDER BY v.rowid DESC LIMIT 1''',
                (ver_table_id,),
            ).fetchone()
        new_blob = compress_version_body(source_proto)
        created_version = False
        created_version_table = False
        if ver and ver["Body"] is not None:
            version_id = ver["ListMgt::LmVersion_id"]
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (new_blob, version_id),
            )
            session.steps.append("replace_grade_body_with_power_grade")
        else:
            if not ver_table_id:
                ver_table_id = _create_lm_version_table_for_item(
                    cursor,
                    item_id=str(clip_id),
                    fields_blob=bytes.fromhex(_VERSION_TABLE_FIELDS_BLOB_HEX),
                )
                created_version_table = True
            version_id = str(_uuid.uuid4())
            _insert_lm_version_from_body(
                cursor,
                body=new_blob,
                version_id=version_id,
                version_table_id=str(ver_table_id),
            )
            created_version = True
            session.steps.append("create_grade_version_from_power_grade")
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_id": version_id,
            "created_version": created_version,
            "created_version_table": created_version_table,
            "readback": state.to_dict(),
        }

    def verifier(_fresh_conn: Any, mutation_result: Any, session: DiskDbMutationSession) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "PowerGrade DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        version_id = mutation_result.get("version_id")
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                'SELECT Body FROM "ListMgt::LmVersion" WHERE "ListMgt::LmVersion_id" = ?',
                (version_id,),
            ).fetchone()
            if not row or not row["Body"]:
                raise APICallFailed(
                    "PowerGrade verification could not read the applied grade body.",
                    details={"version_id": version_id},
                )
            actual_params = _parse_params_from_proto(decompress_version_body(row["Body"]))
        finally:
            connection.close()
        actual_signature = _float_param_signature(actual_params)
        if actual_signature != expected_signature:
            raise APICallFailed(
                "PowerGrade DB apply did not verify after project reload.",
                details={
                    "expected_param_count": len(expected_signature),
                    "actual_param_count": len(actual_signature),
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "param_count": len(actual_signature),
        }

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color power grade db apply",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    if isinstance(result, dict):
        result["db_session_route"] = result.get("route")
        result["route"] = "db_workaround_power_grade_apply"
        result["power_grade"] = {
            "index": selected["index"],
            "label": selected["label"],
            "still_id": selected["still_id"],
            "source_version_id": selected["version_id"],
            "user_db_path": user_db_path,
            "param_count": len(expected_signature),
        }
    return result
