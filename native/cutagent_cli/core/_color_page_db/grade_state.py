"""Grade State helpers for Color Page DB operations."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import sqlite3
import struct
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from ...errors import APICallFailed, ValidationError
from ..db_session import DiskDbMutationSession, execute_sqlite_disk_db_mutation
from ..db_timeline_rows import find_ti_item_row
from .constants import *
from .proto_codec import *
from .version_body import *
from .transforms import *
from .params import *
from .proto_sections import *
from .curves import *
from .hdr import *
from .node_graph import *
from .power_windows import *
from .cst_hsv import *


@dataclass
class ColorGradeState:
    """Current color grade parameters for a clip."""
    clip_name: str
    has_grade: bool = False
    params: list[GradeParam] = field(default_factory=list)
    cst: dict[str, str] = field(default_factory=dict)
    proto_data: bytes | None = None

    # Convenience accessors
    @property
    def lift(self) -> dict[str, float]:
        return {
            "r": self._get(PARAM_LIFT_R, 0.0),
            "g": self._get(PARAM_LIFT_G, 0.0),
            "b": self._get(PARAM_LIFT_B, 0.0),
        }

    @property
    def gamma(self) -> dict[str, float]:
        return {
            "r": self._get(PARAM_GAMMA_R, 0.0),
            "g": self._get(PARAM_GAMMA_G, 0.0),
            "b": self._get(PARAM_GAMMA_B, 0.0),
        }

    @property
    def gain(self) -> dict[str, float]:
        return {
            "r": self._get(PARAM_GAIN_R, 1.0),
            "g": self._get(PARAM_GAIN_G, 1.0),
            "b": self._get(PARAM_GAIN_B, 1.0),
        }

    @property
    def saturation(self) -> float:
        return self._get(PARAM_SATURATION, 1.0)

    @property
    def offset(self) -> dict[str, float]:
        return {
            "r": self._get(PARAM_OFFSET_R, 0.0),
            "g": self._get(PARAM_OFFSET_G, 0.0),
            "b": self._get(PARAM_OFFSET_B, 0.0),
        }

    @property
    def primary(self) -> dict[str, float]:
        return {
            "hue": self._get(PARAM_HUE, 0.0),
            "contrast": self._get(PARAM_CONTRAST, 1.0),
            "pivot": self._get(PARAM_PIVOT, 0.435),
            "temperature": self._get(PARAM_TEMPERATURE, 0.0),
            "tint": self._get(PARAM_TINT, 0.0),
            "lum_mix": self._get(PARAM_LUM_MIX, 1.0),
            "highlights": self._get(PARAM_HIGHLIGHTS, 0.0),
            "shadows": self._get(PARAM_SHADOWS, 0.0),
            "color_boost": self._get(PARAM_COLOR_BOOST, 0.0),
            "mid_detail": self._get(PARAM_MID_DETAIL, 0.0),
        }

    @property
    def hdr(self) -> dict[str, Any] | None:
        return _params_to_hdr_dict(self.params)

    @property
    def key_output(self) -> dict[str, float] | None:
        for param in self.params:
            if param.key == PARAM_KEY_OUTPUT_GAIN:
                return {"gain": float(param.value)}
        return None

    @property
    def curves(self) -> dict[str, dict[str, float]]:
        return _params_to_curves_dict(self.params)

    @property
    def power_windows(self) -> list[dict[str, Any]]:
        windows: list[dict[str, Any]] = []
        by_node: dict[int, list[GradeParam]] = {}
        for param in self.params:
            if param.key in POWER_WINDOW_KEYS:
                by_node.setdefault(param.node_index, []).append(param)
        for node_index, params in sorted(by_node.items()):
            readback = _power_window_readback(params)
            readback["node_index"] = node_index
            windows.append(readback)
        return windows

    @property
    def color_slice(self) -> dict[str, Any] | None:
        from .color_slice import _color_slice_payloads_from_params

        params = [
            param
            for param in self.params
            if param.key in {
                PARAM_COLOR_SLICE_GLOBAL_DEN,
                PARAM_COLOR_SLICE_GLOBAL_DEN_DEPTH,
                PARAM_COLOR_SLICE_GLOBAL_SAT,
                PARAM_COLOR_SLICE_GLOBAL_SAT_BALANCE,
                PARAM_COLOR_SLICE_GLOBAL_SAT_DEPTH,
                PARAM_COLOR_SLICE_GLOBAL_HUE,
                PARAM_COLOR_SLICE_PER_SLICE,
                PARAM_COLOR_SLICE_CENTER,
            }
        ]
        if not params:
            return None
        return _color_slice_payloads_from_params(params)

    @property
    def color_warper(self) -> dict[str, Any] | None:
        from .color_warper import _color_warper_payloads_from_params, _existing_color_warper_state

        if self.proto_data:
            return _existing_color_warper_state(self.proto_data)
        params = [
            param
            for param in self.params
            if param.key in {
                PARAM_COLOR_WARPER_HUE_SAT_WIDTH,
                PARAM_COLOR_WARPER_HUE_SAT_HEIGHT,
                PARAM_COLOR_WARPER_HUE_SAT_SELECTION,
                PARAM_COLOR_WARPER_CHROMA_LUMA_WIDTH,
                PARAM_COLOR_WARPER_CHROMA_LUMA_HEIGHT,
                PARAM_COLOR_WARPER_CHROMA_LUMA_SELECTION,
                PARAM_COLOR_WARPER_MODE,
                PARAM_COLOR_WARPER_SUBMODE,
                PARAM_COLOR_WARPER_CHROMA_STROKE,
                PARAM_COLOR_WARPER_PANEL_MODE,
            }
        ]
        if not params:
            return None
        return _color_warper_payloads_from_params(params)

    def _nodes(self) -> list[dict[str, Any]]:
        nodes = _params_to_node_dicts(self.params)
        if not nodes:
            return []

        from .color_warper import _color_warper_payloads_from_params, _decode_color_warper_meshes

        for node in nodes:
            node_index = int(node["index"])
            node_params = [
                param
                for param in self.params
                if param.node_index == node_index and param.key in {
                    PARAM_COLOR_WARPER_HUE_SAT_WIDTH,
                    PARAM_COLOR_WARPER_HUE_SAT_HEIGHT,
                    PARAM_COLOR_WARPER_HUE_SAT_SELECTION,
                    PARAM_COLOR_WARPER_CHROMA_LUMA_WIDTH,
                    PARAM_COLOR_WARPER_CHROMA_LUMA_HEIGHT,
                    PARAM_COLOR_WARPER_CHROMA_LUMA_SELECTION,
                    PARAM_COLOR_WARPER_MODE,
                    PARAM_COLOR_WARPER_SUBMODE,
                    PARAM_COLOR_WARPER_CHROMA_STROKE,
                    PARAM_COLOR_WARPER_PANEL_MODE,
                }
            ]
            warper = _color_warper_payloads_from_params(node_params) or {}
            if node_index == 1 and self.proto_data:
                warper.update(_decode_color_warper_meshes(self.proto_data))
            if warper:
                node["color_warper"] = warper
        return nodes

    def _get(self, key: int, default: Any) -> Any:
        for p in self.params:
            if p.key == key:
                return p.value
        return default

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "clip": self.clip_name,
            "has_grade": self.has_grade,
            "lift": self.lift,
            "gamma": self.gamma,
            "gain": self.gain,
            "offset": self.offset,
            "saturation": self.saturation,
            "primary": self.primary,
            "curves": self.curves,
            "cst": self.cst,
            "power_windows": self.power_windows,
        }
        hdr = self.hdr
        if hdr:
            result["hdr"] = hdr
        key_output = self.key_output
        if key_output:
            result["key_output"] = key_output
        color_slice = self.color_slice
        if color_slice:
            result["color_slice"] = color_slice
        color_warper = self.color_warper
        if color_warper:
            result["color_warper"] = color_warper
        if self.params:
            result["raw_params"] = [p.to_dict() for p in self.params]
            result["nodes"] = self._nodes()
        return result


def read_color_grade(
    cursor: sqlite3.Cursor,
    *,
    clip_id: str,
    clip_name: str = "",
) -> ColorGradeState:
    """Read current color grade state for a clip from the DB."""
    state = ColorGradeState(clip_name=clip_name)

    # Find the version table for this clip
    row = cursor.execute(
        "SELECT pLmVerTable FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
        (clip_id,),
    ).fetchone()

    if not row or not row["pLmVerTable"]:
        return state

    ver_table_id = row["pLmVerTable"]

    versions = _select_active_grade_version(cursor, str(ver_table_id))

    if not versions or not versions["Body"]:
        return state

    body = versions["Body"]
    proto_data = decompress_version_body(body)
    params = _parse_params_from_proto(proto_data)
    cst = _walk_cst_options(proto_data)

    state.has_grade = True
    state.params = params
    state.cst = cst
    state.proto_data = proto_data
    return state


def read_color_grade_for_clip(
    conn: Any,
    *,
    clip_name: str | None = None,
    include_private_topology: bool = False,
) -> dict[str, Any]:
    """Read current color grade state for a live timeline clip from Project.db."""
    from ..db_timeline_selection import resolve_video_group
    from ...runtime_health import resolve_current_disk_project_db

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    current_database = resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    project_db_path = str(current_database["project_db_path"])

    connection = sqlite3.connect(project_db_path)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        clip_id = str(row["Sm2TiItem_id"])
        state = read_color_grade(cursor, clip_id=clip_id, clip_name=item_ref.name)
    finally:
        connection.close()

    result = {
        "clip": item_ref.name,
        "clip_id": clip_id,
        "project_db_path": project_db_path,
        "current_database": current_database,
        "readback": state.to_dict(),
    }
    if include_private_topology:
        root = _get_submessage(state.proto_data or b"", 1)
        containers = _root_color_node_containers(state.proto_data or b"")
        mixer_types = [
            value
            for container in containers
            if (value := _get_first_varint_field(container, 8)) in {68, 90}
        ]
        if not mixer_types:
            kind = "serial"
        elif mixer_types == [68]:
            kind = "parallel"
        elif mixer_types == [90]:
            kind = "layer"
        else:
            kind = "unknown"
        container_rows = [
            {
                "position": position,
                "sha256": hashlib.sha256(container).hexdigest(),
                "graph_id": _get_first_varint_field(container, 1),
                "node_index": _get_first_varint_field(container, 2),
                "x": _get_first_varint_field(container, 4),
                "y": _get_first_varint_field(container, 5),
                "node_type": _get_first_varint_field(container, 8),
            }
            for position, container in enumerate(containers, 1)
        ]
        edges = sorted(
            _root_graph_edges(root or b""),
            key=lambda edge: json.dumps(edge, sort_keys=True, separators=(",", ":")),
        )
        render_state: dict[str, Any] = {"field9_matches": False, "field10_matches": False, "field12_present": False}
        exact = False
        if root is not None and kind == "serial" and containers:
            graph_ids = [row["graph_id"] for row in container_rows]
            expected_render = _build_serial_render_graph_fields(final_graph_id=int(graph_ids[-1] or 0), tick=0)
            render_state = {
                "field9_matches": _get_first_length_delimited_field(root, 9) is not None if len(containers) == 1 else _get_first_length_delimited_field(root, 9) == _get_first_length_delimited_field(expected_render, 9),
                "field10_matches": _get_first_length_delimited_field(root, 10) is not None if len(containers) == 1 else _get_first_length_delimited_field(root, 10) == _get_first_length_delimited_field(expected_render, 10),
                "field12_present": _get_first_varint_field(root, 12) is not None,
            }
            expected_edges = [
                {"1": int(source), "3": int(target), "5": 64, "6": 64, "7": slot}
                for slot, (source, target) in enumerate(zip(graph_ids, graph_ids[1:]), 1)
                if source is not None and target is not None
            ]
            exact = (
                all(
                    row["graph_id"] == row["node_index"]
                    and row["node_type"] == 44
                    and row["x"] == 190 + max(0, int(row["node_index"] or 1) - 1) * 328
                    and row["y"] == 180
                    for row in container_rows
                )
                and [row["node_index"] for row in container_rows] == list(range(1, len(containers) + 1))
                and edges == expected_edges
                and all(render_state.values())
            )
        elif root is not None and kind in {"parallel", "layer"} and len(container_rows) == 3:
            primary, mixer, branch = container_rows
            canonical_containers = (
                primary["graph_id"] == 1 and primary["node_index"] == 1 and primary["node_type"] == 44
                and primary["x"] == 190 and primary["y"] == 180
                and mixer["graph_id"] == 3 and mixer["node_index"] == 3 and mixer["node_type"] == (68 if kind == "parallel" else 90)
                and mixer["x"] == 518 and mixer["y"] == 180
                and branch["graph_id"] == 4 and branch["node_index"] == 2 and branch["node_type"] == 44
                and branch["x"] == 190 and branch["y"] == 416
            )
            if kind == "layer" and primary["graph_id"] is not None:
                render_state = _read_layer_mixer_render_graph_state(
                    root,
                    primary_graph_id=int(primary["graph_id"]),
                    branch_graph_id=4,
                    mixer_graph_id=3,
                )
                expected_edges = [
                    {"1": int(primary["graph_id"]), "3": 3, "5": 64, "6": 64, "7": 2},
                    {"1": 4, "3": 3, "4": 1, "5": 64, "6": 64, "7": 3},
                ]
                exact = canonical_containers and edges == expected_edges and bool(render_state.get("field9_matches") and render_state.get("field10_matches") and render_state.get("field12_present"))
            else:
                render_state = {
                    "field9_matches": _get_first_length_delimited_field(root, 9) is not None,
                    "field10_matches": _get_first_length_delimited_field(root, 10) is not None,
                    "field12_present": _get_first_varint_field(root, 12) is not None,
                }
                exact = canonical_containers and edges == [] and all(render_state.values())
        field9 = _get_first_length_delimited_field(root, 9) if root is not None else None
        field10 = _get_first_length_delimited_field(root, 10) if root is not None else None
        render_state["field9_sha256"] = hashlib.sha256(field9).hexdigest() if field9 is not None else None
        render_state["field10_sha256"] = hashlib.sha256(field10).hexdigest() if field10 is not None else None
        structure = {"containers": container_rows, "edges": edges, "render": render_state}
        structure_sha256 = hashlib.sha256(
            json.dumps(structure, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        result["topology_state"] = {
            "kind": kind,
            "node_count": len(containers),
            "exact": exact,
            "structure_sha256": structure_sha256,
            **structure,
        }
        from .. import resolvefx_db

        result["resolvefx_by_node"] = {
            str(index): resolvefx_db.read_resolvefx_state(
                state.proto_data or b"",
                node_index=index,
            ).get("plugin_id")
            for index in range(1, len(containers) + 1)
        }
    return result


def _normalize_grade_state_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {str(key): _normalize_grade_state_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [_normalize_grade_state_value(item) for item in value]
        if all(isinstance(item, dict) for item in normalized):
            return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        return normalized
    return value


def _grade_state_signature(readback: dict[str, Any]) -> dict[str, Any]:
    state = dict(readback.get("readback") or readback)
    state.pop("clip", None)
    normalized = _normalize_grade_state_value(state)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "has_grade": bool(state.get("has_grade")),
        "raw_param_count": len(state.get("raw_params") or []),
        "normalized": normalized,
    }


def _next_db_saved_time(cursor: sqlite3.Cursor) -> int:
    row = cursor.execute('SELECT COALESCE(MAX("DbSavedTime"), 0) + 1 FROM "ListMgt::LmVersionTable"').fetchone()
    return int(row[0] or int(time.time() * 1000))


def _select_active_grade_version(cursor: sqlite3.Cursor, version_table_id: str) -> sqlite3.Row | None:
    row = cursor.execute(
        '''
        SELECT v.*
        FROM "ListMgt::LmVersion" v
        JOIN "ListMgt::LmVersionTable" vt
          ON vt.pActive = v."ListMgt::LmVersion_id"
        WHERE vt."ListMgt::LmVersionTable_id" = ?
        LIMIT 1
        ''',
        (version_table_id,),
    ).fetchone()
    if row is not None:
        return row
    row = cursor.execute(
        '''
        SELECT v.*
        FROM "ListMgt::LmVersion" v
        JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
          ON rel.DbAssociate = v."ListMgt::LmVersion_id"
        WHERE rel.DbOwner = ? AND v.HasCorrection = 1
        ORDER BY rel.DbIndex DESC, v.rowid DESC
        LIMIT 1
        ''',
        (version_table_id,),
    ).fetchone()
    if row is not None:
        return row
    return cursor.execute(
        '''
        SELECT v.*
        FROM "ListMgt::LmVersion" v
        JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
          ON rel.DbAssociate = v."ListMgt::LmVersion_id"
        WHERE rel.DbOwner = ?
        ORDER BY rel.DbIndex DESC, v.rowid DESC
        LIMIT 1
        ''',
        (version_table_id,),
    ).fetchone()


def _select_active_grade_version_for_clip(cursor: sqlite3.Cursor, clip_id: str) -> sqlite3.Row | None:
    row = cursor.execute(
        'SELECT pLmVerTable FROM Sm2TiItem WHERE Sm2TiItem_id = ?',
        (clip_id,),
    ).fetchone()
    if row is None or not row["pLmVerTable"]:
        return None
    return _select_active_grade_version(cursor, str(row["pLmVerTable"]))


def _copy_lm_version_columns(
    cursor: sqlite3.Cursor,
    *,
    source_version: sqlite3.Row,
    target_version_id: str,
    target_table_id: str,
) -> None:
    cursor.execute(
        '''
        UPDATE "ListMgt::LmVersion"
        SET
          Name = ?,
          HasCorrection = 1,
          VerType = ?,
          ImplVersion = ?,
          IncludedInRecording = ?,
          FlatPassEnabled = ?,
          RGBAOutputEnabled = ?,
          Body = ?,
          "ListMgt::LmVersionTable_id" = ?,
          UseVersionClipProcParams = ?,
          UserClipProcParams = ?,
          Sm2Group_id = ?,
          FieldsBlob = ?
        WHERE "ListMgt::LmVersion_id" = ?
        ''',
        (
            source_version["Name"],
            source_version["VerType"],
            source_version["ImplVersion"],
            source_version["IncludedInRecording"],
            source_version["FlatPassEnabled"],
            source_version["RGBAOutputEnabled"],
            source_version["Body"],
            target_table_id,
            source_version["UseVersionClipProcParams"],
            source_version["UserClipProcParams"],
            source_version["Sm2Group_id"],
            source_version["FieldsBlob"],
            target_version_id,
        ),
    )


def _insert_lm_version_copy(
    cursor: sqlite3.Cursor,
    *,
    source_version: sqlite3.Row,
    target_version_id: str,
    target_table_id: str,
) -> None:
    cursor.execute(
        '''
        INSERT INTO "ListMgt::LmVersion" (
          "ListMgt::LmVersion_id", DbType, "Gallery::GyStill_id", Name, HasCorrection,
          VerType, ImplVersion, IncludedInRecording, FlatPassEnabled, RGBAOutputEnabled,
          Body, "ListMgt::LmVersionTable_id", UseVersionClipProcParams,
          UserClipProcParams, Sm2Group_id, FieldsBlob
        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            target_version_id,
            source_version["DbType"],
            source_version["Gallery::GyStill_id"],
            source_version["Name"],
            source_version["VerType"],
            source_version["ImplVersion"],
            source_version["IncludedInRecording"],
            source_version["FlatPassEnabled"],
            source_version["RGBAOutputEnabled"],
            source_version["Body"],
            target_table_id,
            source_version["UseVersionClipProcParams"],
            source_version["UserClipProcParams"],
            source_version["Sm2Group_id"],
            source_version["FieldsBlob"],
        ),
    )


def _create_lm_version_table_for_item(
    cursor: sqlite3.Cursor,
    *,
    item_id: str,
    ver_type: str = "0",
    fields_blob: bytes | None = None,
) -> str:
    version_table_id = str(uuid.uuid4())
    cursor.execute(
        '''
        INSERT INTO "ListMgt::LmVersionTable" (
          "ListMgt::LmVersionTable_id", DbType, SM_VideoTrack_id, VerType,
          pRemoteTable, pActive, SM_Clip_id, Sm2MpMedia_id, Sm2Sequence_id,
          Sm2TiItem_id, FieldsBlob, DbSavedTime, LinkedGroup, Sm2Group_id
        ) VALUES (?, 'ListMgt::LmVersionTable', NULL, ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL)
        ''',
        (
            version_table_id,
            ver_type,
            item_id,
            fields_blob,
            _next_db_saved_time(cursor),
        ),
    )
    cursor.execute(
        "UPDATE Sm2TiItem SET pLmVerTable = ? WHERE Sm2TiItem_id = ?",
        (version_table_id, item_id),
    )
    return version_table_id


def _insert_lm_version_from_body(
    cursor: sqlite3.Cursor,
    *,
    body: bytes,
    version_id: str,
    version_table_id: str,
    ver_type: str = "0",
    fields_blob: bytes | None = None,
) -> None:
    cursor.execute(
        '''
        INSERT INTO "ListMgt::LmVersion" (
          "ListMgt::LmVersion_id", DbType, "Gallery::GyStill_id", Name, HasCorrection,
          VerType, ImplVersion, IncludedInRecording, FlatPassEnabled, RGBAOutputEnabled,
          Body, "ListMgt::LmVersionTable_id", UseVersionClipProcParams,
          UserClipProcParams, Sm2Group_id, FieldsBlob
        ) VALUES (?, 'ListMgt::LmVersion', NULL, 'Version 1', 1, ?, 1, 1, 0, 0, ?, ?, 0, NULL, NULL, ?)
        ''',
        (
            version_id,
            ver_type,
            body,
            version_table_id,
            fields_blob,
        ),
    )
    cursor.execute(
        '''
        INSERT INTO "ListMgt::LmVersion_ListMgt::LmVersionTable"
          (DbOwner, DbAssociate, DbPropertyName, DbIndex)
        VALUES (?, ?, 'Locals', 0)
        ''',
        (version_table_id, version_id),
    )
    cursor.execute(
        '''
        UPDATE "ListMgt::LmVersionTable"
        SET pActive = ?, VerType = ?, DbSavedTime = ?
        WHERE "ListMgt::LmVersionTable_id" = ?
        ''',
        (version_id, ver_type, _next_db_saved_time(cursor), version_table_id),
    )


def copy_color_grade_db(
    conn: Any,
    *,
    source_name: str,
    target_names: list[str],
) -> dict[str, Any]:
    """Copy a Color Page grade between timeline items via Project.db and verify after reload."""
    from ..db_timeline_selection import resolve_video_group

    source_ref = resolve_video_group(conn, clip_name=source_name)["video"]
    target_refs = [resolve_video_group(conn, clip_name=target_name)["video"] for target_name in target_names]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        source_row = find_ti_item_row(
            cursor,
            item=source_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
        source_table_id = source_row.get("pLmVerTable")
        if not source_table_id:
            raise ValidationError(
                "Source clip has no Color Page grade version table to copy.",
                details={"source": source_ref.name},
                recoverability="not_applicable",
            )

        source_version = cursor.execute(
            '''
            SELECT v.*
            FROM "ListMgt::LmVersion" v
            JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
              ON rel.DbAssociate = v."ListMgt::LmVersion_id"
            WHERE rel.DbOwner = ? AND v.HasCorrection = 1 AND v.Body IS NOT NULL
            ORDER BY rel.DbIndex DESC, v.rowid DESC
            LIMIT 1
            ''',
            (source_table_id,),
        ).fetchone()
        if source_version is None or not source_version["Body"]:
            raise ValidationError(
                "Source clip has no graded Color Page payload to copy.",
                details={"source": source_ref.name, "source_version_table_id": source_table_id},
                recoverability="not_applicable",
            )

        source_table = cursor.execute(
            'SELECT * FROM "ListMgt::LmVersionTable" WHERE "ListMgt::LmVersionTable_id" = ?',
            (source_table_id,),
        ).fetchone()
        if source_table is None:
            raise ValidationError(
                "Source clip grade version table is missing from Project.db.",
                details={"source": source_ref.name, "source_version_table_id": source_table_id},
                recoverability="not_applicable",
            )

        copied_targets: list[dict[str, Any]] = []
        for target_ref in target_refs:
            target_row = find_ti_item_row(
                cursor,
                item=target_ref,
                db_type="Sm2TiVideoClip",
                timeline_name=timeline_name,
            )
            target_item_id = str(target_row["Sm2TiItem_id"])
            target_table_id = target_row.get("pLmVerTable")
            created_table = False
            created_version = False

            if not target_table_id:
                target_table_id = str(uuid.uuid4())
                cursor.execute(
                    '''
                    INSERT INTO "ListMgt::LmVersionTable" (
                      "ListMgt::LmVersionTable_id", DbType, SM_VideoTrack_id, VerType,
                      pRemoteTable, pActive, SM_Clip_id, Sm2MpMedia_id, Sm2Sequence_id,
                      Sm2TiItem_id, FieldsBlob, DbSavedTime, LinkedGroup, Sm2Group_id
                    ) VALUES (?, 'ListMgt::LmVersionTable', NULL, ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL)
                    ''',
                    (
                        target_table_id,
                        source_table["VerType"],
                        target_item_id,
                        source_table["FieldsBlob"],
                        _next_db_saved_time(cursor),
                    ),
                )
                cursor.execute(
                    "UPDATE Sm2TiItem SET pLmVerTable = ? WHERE Sm2TiItem_id = ?",
                    (target_table_id, target_item_id),
                )
                created_table = True

            target_version = _select_active_grade_version(cursor, str(target_table_id))
            if target_version is None:
                target_version_id = str(uuid.uuid4())
                _insert_lm_version_copy(
                    cursor,
                    source_version=source_version,
                    target_version_id=target_version_id,
                    target_table_id=str(target_table_id),
                )
                cursor.execute(
                    '''
                    INSERT INTO "ListMgt::LmVersion_ListMgt::LmVersionTable"
                      (DbOwner, DbAssociate, DbPropertyName, DbIndex)
                    VALUES (?, ?, 'Locals', 0)
                    ''',
                    (target_table_id, target_version_id),
                )
                created_version = True
            else:
                target_version_id = str(target_version["ListMgt::LmVersion_id"])
                _copy_lm_version_columns(
                    cursor,
                    source_version=source_version,
                    target_version_id=target_version_id,
                    target_table_id=str(target_table_id),
                )

            cursor.execute(
                '''
                UPDATE "ListMgt::LmVersionTable"
                SET pActive = ?, VerType = ?, DbSavedTime = ?
                WHERE "ListMgt::LmVersionTable_id" = ?
                ''',
                (target_version_id, source_table["VerType"], _next_db_saved_time(cursor), target_table_id),
            )
            copied_targets.append(
                {
                    "target": target_ref.name,
                    "clip_id": target_item_id,
                    "version_table_id": str(target_table_id),
                    "version_id": target_version_id,
                    "created_version_table": created_table,
                    "created_version": created_version,
                }
            )

        session.steps.append("copy_color_grade_versions")
        return {
            "source": source_ref.name,
            "source_clip_id": str(source_row["Sm2TiItem_id"]),
            "source_version_table_id": str(source_table_id),
            "source_version_id": str(source_version["ListMgt::LmVersion_id"]),
            "targets": copied_targets,
            "copied_count": len(copied_targets),
            "grade_copy_route": "db_workaround_color_grade_copy",
        }

    def verifier(
        fresh_conn: Any,
        mutation_result: Any,
        session: DiskDbMutationSession,
    ) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed("Color grade copy mutation did not return a payload for verification.")
        source_readback = read_color_grade_for_clip(fresh_conn, clip_name=source_name)
        source_signature = _grade_state_signature(source_readback)
        target_results: list[dict[str, Any]] = []
        mismatches: list[dict[str, Any]] = []
        for target_name in target_names:
            target_readback = read_color_grade_for_clip(fresh_conn, clip_name=target_name)
            target_signature = _grade_state_signature(target_readback)
            matches = target_signature["sha256"] == source_signature["sha256"]
            result = {
                "target": target_name,
                "clip_id": target_readback.get("clip_id"),
                "matches_source": matches,
                "signature_sha256": target_signature["sha256"],
                "has_grade": target_signature["has_grade"],
                "raw_param_count": target_signature["raw_param_count"],
            }
            target_results.append(result)
            if not matches:
                mismatches.append(result)

        verification = {
            "status": "verified" if not mismatches else "failed",
            "route": "db_workaround_color_grade_copy_readback",
            "source": {
                "clip": source_name,
                "clip_id": source_readback.get("clip_id"),
                "signature_sha256": source_signature["sha256"],
                "has_grade": source_signature["has_grade"],
                "raw_param_count": source_signature["raw_param_count"],
            },
            "targets": target_results,
        }
        if mismatches:
            raise APICallFailed(
                "Color grade DB copy did not verify after project reload.",
                details={
                    "source": source_name,
                    "targets": target_names,
                    "verification": verification,
                    "project_db_path": session.project_db_path,
                },
                recoverability="manual",
            )
        return verification

    result = execute_sqlite_disk_db_mutation(
        conn,
        context="color grade copy db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    result["db_session_route"] = result.get("route")
    result["route"] = "db_workaround_color_grade_copy"
    return result


__all__ = (
    'ColorGradeState',
    'read_color_grade',
    'read_color_grade_for_clip',
    '_normalize_grade_state_value',
    '_grade_state_signature',
    '_next_db_saved_time',
    '_select_active_grade_version',
    '_select_active_grade_version_for_clip',
    '_copy_lm_version_columns',
    '_insert_lm_version_copy',
    '_create_lm_version_table_for_item',
    '_insert_lm_version_from_body',
    'copy_color_grade_db',
)
