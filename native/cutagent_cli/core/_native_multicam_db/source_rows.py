from __future__ import annotations

from dataclasses import asdict
import os
import re
import sqlite3
from typing import Any

from ...errors import ValidationError


def _fetch_folder_paths(cursor: sqlite3.Cursor) -> dict[str, str]:
    rows = cursor.execute(
        """
        SELECT
            Sm2MpFolder_id,
            Name,
            MpFolder,
            Sm2MpFolder_Owner_id
        FROM Sm2MpFolder
        """
    ).fetchall()
    folder_rows = {
        str(row[0]): {
            "id": str(row[0]),
            "name": str(row[1] or ""),
            "parent": str(row[2] or row[3] or "") or None,
        }
        for row in rows
        if row[0]
    }

    cache: dict[str, str] = {}

    def build_path(folder_id: str, stack: set[str] | None = None) -> str:
        if folder_id in cache:
            return cache[folder_id]
        stack = stack or set()
        if folder_id in stack:
            return folder_rows[folder_id]["name"]
        stack.add(folder_id)
        folder = folder_rows[folder_id]
        name = folder["name"]
        parent_id = folder["parent"]
        if parent_id and parent_id in folder_rows and parent_id != folder_id:
            parent_path = build_path(parent_id, stack)
            cache[folder_id] = f"{parent_path}/{name}" if parent_path else name
        else:
            cache[folder_id] = name
        stack.remove(folder_id)
        return cache[folder_id]

    for folder_id in folder_rows:
        build_path(folder_id)
    return cache


def _is_temp_bin_folder_path(folder_path: str | None, *, temp_bin_prefix: str) -> bool:
    normalized = str(folder_path or "")
    return f"/{temp_bin_prefix}" in normalized or normalized.startswith(temp_bin_prefix)


def _normalize_folder_path_for_match(value: str | None) -> str:
    return re.sub(r"/+", "/", str(value or "").strip().replace("\\", "/")).strip("/")


def _normalize_source_path_for_match(value: str | None) -> str:
    expanded = os.path.expanduser(str(value or "").strip())
    if not expanded:
        return ""
    return os.path.normcase(os.path.normpath(expanded))


def _folder_leaf(value: str | None) -> str:
    normalized = _normalize_folder_path_for_match(value)
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]


def _first_frame_value(row: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        raw_value = row.get(key)
        if raw_value in (None, ""):
            continue
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            continue
    return None


def _source_path_matches(candidate: str | None, requested: str | None) -> bool:
    candidate_normalized = _normalize_source_path_for_match(candidate)
    requested_normalized = _normalize_source_path_for_match(requested)
    if not candidate_normalized or not requested_normalized:
        return False
    return candidate_normalized == requested_normalized


def _folder_path_matches_exact(candidate: str | None, requested: str | None) -> bool:
    candidate_normalized = _normalize_folder_path_for_match(candidate)
    requested_normalized = _normalize_folder_path_for_match(requested)
    if not candidate_normalized or not requested_normalized:
        return False
    return candidate_normalized == requested_normalized


def _folder_path_matches_suffix(candidate: str | None, requested: str | None) -> bool:
    candidate_normalized = _normalize_folder_path_for_match(candidate)
    requested_normalized = _normalize_folder_path_for_match(requested)
    if not candidate_normalized or not requested_normalized:
        return False
    return (
        candidate_normalized == requested_normalized
        or candidate_normalized.endswith(f"/{requested_normalized}")
    )


def _preferred_project_folder_matches(
    candidates: list[Any],
    *,
    project_folder_name: str | None,
) -> list[Any]:
    normalized_project_name = str(project_folder_name or "").strip().lower()
    if not normalized_project_name:
        return []
    return [
        row
        for row in candidates
        if normalized_project_name in [part.lower() for part in _normalize_folder_path_for_match(row.folder_path).split("/") if part]
    ]


def _representative_media_file_path(cursor: sqlite3.Cursor, *, media_id: str) -> str | None:
    row = cursor.execute(
        """
        SELECT MediaFilePath
        FROM Sm2TiItem
        WHERE MediaRef = ?
          AND MediaFilePath IS NOT NULL
          AND TRIM(MediaFilePath) != ''
        ORDER BY
          CASE
            WHEN MediaTrackIdx IS NULL OR MediaTrackIdx = 0 THEN 0
            ELSE 1
          END,
          rowid DESC
        LIMIT 1
        """,
        (media_id,),
    ).fetchone()
    if not row or row[0] in (None, ""):
        return None
    return str(row[0])


def _build_resolution_entry(
    *,
    row: Any,
    requested_folder: str,
    requested_source_path: str,
    strategy: str,
) -> dict[str, Any]:
    return {
        "media_id": row.media_id,
        "clip_name": row.name,
        "folder_path": row.folder_path,
        "source_path": row.source_path,
        "strategy": strategy,
        "requested_folder": requested_folder or None,
        "requested_source_path": requested_source_path or None,
    }


def resolve_source_media_rows(
    project_db_path: str,
    *,
    resolved_angles: list[dict[str, Any]],
    resolved_db_media_row_cls: type,
    row_to_dict_fn,
    temp_bin_prefix: str,
    return_diagnostics: bool = False,
) -> list[Any]:
    connection = sqlite3.connect(project_db_path)
    try:
        cursor = connection.cursor()
        folder_paths = _fetch_folder_paths(cursor)
        project_folder_name = str(getattr(getattr(project_db_path, "parent", None), "name", "") or "")
        if not project_folder_name:
            project_folder_name = os.path.basename(os.path.dirname(str(project_db_path)))
        out: list[Any] = []
        diagnostics: list[dict[str, Any]] = []

        for angle in resolved_angles:
            clip_name = str(angle.get("clip_name") or "").strip()
            folder_path = str(angle.get("folder") or "").strip()
            source_path = str(angle.get("source_path") or "").strip()
            media_columns = {
                str(row[1])
                for row in cursor.execute("PRAGMA table_info(Sm2MpMedia)").fetchall()
            }
            optional_mark_columns = [
                name
                for name in ("MarkIn", "MarkOut", "MarkInVideo", "MarkOutVideo", "MarkInAudio", "MarkOutAudio")
                if name in media_columns
            ]
            selected_columns = [
                "Sm2MpMedia_id",
                "DbType",
                "Name",
                "Sm2MpFolder_id",
                "CurPlayheadPosition",
                "SlateTC",
                *optional_mark_columns,
            ]
            raw_rows = cursor.execute(
                f"""
                SELECT {", ".join(selected_columns)}
                FROM Sm2MpMedia
                WHERE Name = ?
                  AND DbType NOT IN ('Sm2MpMulticamClip', 'Sm2MpTimeline')
                """,
                (clip_name,),
            ).fetchall()
            column_names = [column[0] for column in list(cursor.description or [])]
            row_dicts = [
                {column_names[index]: value for index, value in enumerate(raw_row)}
                for raw_row in raw_rows
            ]
            candidates = []
            supported_fields = set(getattr(resolved_db_media_row_cls, "__dataclass_fields__", {}))
            for row in row_dicts:
                candidate_kwargs = {
                    "media_id": str(row["Sm2MpMedia_id"]),
                    "name": str(row["Name"] or ""),
                    "folder_id": str(row["Sm2MpFolder_id"] or "") or None,
                    "folder_path": folder_paths.get(str(row["Sm2MpFolder_id"] or ""), ""),
                    "db_type": str(row["DbType"] or ""),
                    "source_path": _representative_media_file_path(
                        cursor,
                        media_id=str(row["Sm2MpMedia_id"]),
                    )
                    or source_path
                    or None,
                    "duration_frames": (
                        int(angle.get("duration_frames"))
                        if angle.get("duration_frames") not in (None, "")
                        else None
                    ),
                    "fps": float(angle.get("fps")) if angle.get("fps") not in (None, "") else None,
                    "cur_playhead_position": (
                        str(row["CurPlayheadPosition"])
                        if row["CurPlayheadPosition"] is not None
                        else None
                    ),
                    "slate_tc": str(row["SlateTC"]) if row["SlateTC"] is not None else None,
                    "media_start_time": (
                        float(angle.get("media_start_time"))
                        if angle.get("media_start_time") not in (None, "")
                        else None
                    ),
                }
                if "audio_mapping" in supported_fields:
                    candidate_kwargs["audio_mapping"] = (
                        dict(angle.get("audio_mapping"))
                        if isinstance(angle.get("audio_mapping"), dict)
                        else None
                    )
                if "mark_in_frame" in supported_fields:
                    candidate_kwargs["mark_in_frame"] = _first_frame_value(
                        row,
                        ("MarkIn", "MarkInVideo", "MarkInAudio"),
                    )
                if "mark_out_frame" in supported_fields:
                    candidate_kwargs["mark_out_frame"] = _first_frame_value(
                        row,
                        ("MarkOut", "MarkOutVideo", "MarkOutAudio"),
                    )
                candidates.append(resolved_db_media_row_cls(**candidate_kwargs))

            stable_candidates = [
                row for row in candidates if not _is_temp_bin_folder_path(row.folder_path, temp_bin_prefix=temp_bin_prefix)
            ]
            chosen_pool = stable_candidates or candidates
            match_strategy = "unique_stable_candidate" if stable_candidates else "unique_candidate"

            if source_path:
                source_path_matches = [
                    row for row in chosen_pool if _source_path_matches(row.source_path, source_path)
                ]
                if source_path_matches:
                    chosen_pool = source_path_matches
                    match_strategy = "exact_source_path"

            if len(chosen_pool) > 1 and folder_path:
                exact_folder_matches = [
                    row for row in chosen_pool if _folder_path_matches_exact(row.folder_path, folder_path)
                ]
                if exact_folder_matches:
                    chosen_pool = exact_folder_matches
                    match_strategy = "exact_folder_path"

            if len(chosen_pool) > 1 and folder_path:
                suffix_folder_matches = [
                    row for row in chosen_pool if _folder_path_matches_suffix(row.folder_path, folder_path)
                ]
                if suffix_folder_matches:
                    chosen_pool = suffix_folder_matches
                    match_strategy = "suffix_folder_path"

            if len(chosen_pool) > 1 and folder_path:
                requested_folder_leaf = _folder_leaf(folder_path)
                if requested_folder_leaf:
                    folder_leaf_matches = [
                        row for row in chosen_pool if _folder_leaf(row.folder_path).lower() == requested_folder_leaf.lower()
                    ]
                    if folder_leaf_matches:
                        chosen_pool = folder_leaf_matches
                        match_strategy = "folder_leaf"

            if len(chosen_pool) > 1:
                project_folder_matches = _preferred_project_folder_matches(
                    chosen_pool,
                    project_folder_name=project_folder_name,
                )
                if project_folder_matches:
                    chosen_pool = project_folder_matches
                    match_strategy = "project_folder_preference"

            if len(chosen_pool) != 1:
                raise ValidationError(
                    "Could not resolve a unique source clip row inside Project.db.",
                    details={
                        "reason": "ambiguous_source_media_row",
                        "clip_name": clip_name,
                        "folder": folder_path,
                        "source_path": source_path,
                        "candidates": [asdict(item) for item in chosen_pool],
                        "project_folder_name": project_folder_name or None,
                    },
                )
            chosen_row = chosen_pool[0]
            out.append(chosen_row)
            diagnostics.append(
                _build_resolution_entry(
                    row=chosen_row,
                    requested_folder=folder_path,
                    requested_source_path=source_path,
                    strategy=match_strategy,
                )
            )

        if return_diagnostics:
            return [
                {"row": row, "resolution": resolution}
                for row, resolution in zip(out, diagnostics)
            ]
        return out
    finally:
        connection.close()
