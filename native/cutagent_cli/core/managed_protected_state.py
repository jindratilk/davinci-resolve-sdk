"""Private canonical protected-family attestation for managed timeline authoring."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import struct
import zlib
from typing import Any

from ..errors import ValidationError
from .native_multicam_db import resolve_disk_project_db_path
from .sdk_live_inspection import documented_unique_id


_PROTECTED_PROPERTY_TOKENS = ("color", "effect", "fusion", "fairlight", "transition", "composite", "opacity")
_COLOR_TABLES = ("ListMgt::LmVersion", "ListMgt::LmVersionTable", "ListMgt::LmVersion_ListMgt::LmVersionTable")
_SEQUENCE_VOLATILE_TIME_FIELDS = {"ModTimeInSecs", "LastModTimeForCache"}
# Exact neighbor fences observed around edit-generation bookkeeping in Resolve 21.1.
# Any missing, duplicate, or reordered record makes the whole model fail closed as raw bytes.
_SEQUENCE_VOLATILE_MODEL_RECORDS = {
    902: (901, 903),
    904: (903, 905),
    1253: (1246, 1254),
    1260: (1259, 1261),
}
_ACTIVE_SEQUENCE_DERIVED_CACHE_FIELDS = {"AuxRenderCacheBA", "RenderCacheBA"}


def _canonical_fl_studio_model(value: bytes) -> Any:
    raw_model = bytes(value)
    try:
        if len(raw_model) < 7 or struct.unpack_from(">I", raw_model, 1)[0] != len(raw_model) - 5:
            return raw_model
        zlib_offset = raw_model.find(b"\x78\x9c", 5)
        if zlib_offset < 0:
            return raw_model
        decoder = zlib.decompressobj()
        model = bytearray(decoder.decompress(raw_model[zlib_offset:]))
        if not decoder.eof:
            return raw_model
        suffix = decoder.unused_data
        compressed_size = len(raw_model[zlib_offset:]) - len(suffix)
        if compressed_size <= 0:
            return raw_model
        for record_id, (previous_id, next_id) in _SEQUENCE_VOLATILE_MODEL_RECORDS.items():
            marker = struct.pack("<iii", 1, record_id, 1)
            positions = []
            cursor = 0
            while True:
                position = model.find(marker, cursor)
                if position < 0:
                    break
                previous = struct.pack("<iii", 1, previous_id, 1)
                following = struct.pack("<iii", 1, next_id, 1)
                if (position >= 16 and position + 32 <= len(model)
                        and model[position - 16:position - 4] == previous
                        and model[position + 16:position + 28] == following):
                    positions.append(position)
                cursor = position + 1
            if len(positions) != 1 or positions[0] + 16 > len(model):
                return raw_model
            model[positions[0] + 12:positions[0] + 16] = b"\0" * 4
        return {
            "valuePrefix": raw_model[:1],
            "modelPrefix": raw_model[5:zlib_offset],
            "model": bytes(model),
            "suffix": suffix,
        }
    except (struct.error, zlib.error):
        return raw_model


def _parse_fields_blob(blob: Any) -> tuple[bytes, int, list[dict[str, Any]]] | None:
    data = bytes(blob or b"")
    if len(data) < 8:
        return None
    try:
        version, count = struct.unpack_from(">II", data, 0)
        if count < 1 or count > 4096:
            return None
        offset = 8
        entries: list[dict[str, Any]] = []
        for _ in range(count):
            key_size = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            if key_size < 2 or key_size % 2 or offset + key_size + 4 > len(data):
                return None
            key = data[offset:offset + key_size].decode("utf-16-be")
            offset += key_size
            value_type = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            value_start = offset
            if value_type == 1:
                offset += 2
            elif value_type in (2, 3):
                offset += 5
            elif value_type in (4, 0x26):
                offset += 9
            elif value_type in (0x0A, 0x0C, 0x10):
                if offset + 5 > len(data):
                    return None
                offset += 5 + struct.unpack_from(">I", data, offset + 1)[0]
            else:
                return None
            if offset > len(data):
                return None
            entries.append({"key": key, "valueType": value_type, "value": data[value_start:offset]})
        if offset != len(data) or len({entry["key"] for entry in entries}) != len(entries):
            return None
        return data, version, entries
    except (UnicodeDecodeError, struct.error):
        return None


def _canonical_sequence_fields_blob(blob: Any) -> Any:
    """Remove only reviewed edit-bookkeeping values from an active sequence blob."""
    parsed = _parse_fields_blob(blob)
    if parsed is None:
        return bytes(blob or b"")
    data, version, entries = parsed
    try:
        normalized = []
        changed = False
        for entry in entries:
            value: Any = entry["value"]
            if (entry["key"] in _SEQUENCE_VOLATILE_TIME_FIELDS
                    and entry["valueType"] == 4 and len(entry["value"]) == 9):
                changed = True
                continue
            elif entry["key"] == "FLStudioModelBA" and entry["valueType"] == 0x0C:
                value = _canonical_fl_studio_model(entry["value"])
            elif entry["key"] == "Thumbnail" and entry["valueType"] == 0x0C:
                value = {"reviewedDerivedTimelineThumbnail": True}
            changed = changed or value is not entry["value"]
            normalized.append({"key": entry["key"], "valueType": entry["valueType"], "value": value})
        return {"version": version, "entries": normalized} if changed else data
    except zlib.error:
        return data


def _canonical_track_fields_blob(blob: Any) -> Any:
    """Remove only the reviewed active-track sequence-cache membership flag."""
    parsed = _parse_fields_blob(blob)
    if parsed is None:
        return bytes(blob or b"")
    data, version, entries = parsed
    retained = [entry for entry in entries if not (
        entry["key"] == "ExcludeTrackFromSequenceCaching"
        and entry["valueType"] == 1
        and entry["value"] in (b"\0\0", b"\0\1")
    )]
    return {"version": version, "entries": retained}


def _canonical_active_sequence_row(
    row: dict[str, Any],
    timeline_resolution: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Normalize only shape-checked values regenerated by an active Timeline edit."""
    result = dict(row)
    saved_time = result.get("DbSavedTime")
    ui_state = result.get("UIElementsState")
    if isinstance(saved_time, int) and not isinstance(saved_time, bool) and saved_time >= 0:
        result["DbSavedTime"] = {"reviewedDerivedSaveTime": True}
    if ui_state is None or (isinstance(ui_state, bytes) and len(ui_state) <= 16 * 1024 * 1024):
        result["UIElementsState"] = {"reviewedActiveTimelineUiState": True}
    for key in _ACTIVE_SEQUENCE_DERIVED_CACHE_FIELDS:
        value = result.get(key)
        if isinstance(value, bytes) and len(value) <= 16 * 1024 * 1024:
            result[key] = {"reviewedDerivedSequenceValue": key}
    media_extents = result.get("MediaExtents")
    if isinstance(media_extents, bytes) and 16 <= len(media_extents) <= 16 * 1024 * 1024:
        try:
            start_seconds, duration_seconds = struct.unpack("<dd", media_extents[:16])
            if math.isfinite(start_seconds) and math.isfinite(duration_seconds) and duration_seconds >= 0:
                result["MediaExtents"] = {"reviewedDerivedSequenceValue": "MediaExtents"}
        except struct.error:
            pass
    result["FieldsBlob"] = _canonical_sequence_fields_blob(result.get("FieldsBlob"))
    raw_resolution = result.get("Resolution")
    if timeline_resolution is not None and isinstance(raw_resolution, bytes) and len(raw_resolution) == 16:
        stored_resolution = dict(zip(("width", "height"), struct.unpack(">QQ", raw_resolution)))
        if stored_resolution == {"width": 0, "height": 0} or stored_resolution == timeline_resolution:
            result["Resolution"] = {"reviewedTimelineResolution": timeline_resolution}
    return result


def _canonical(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=lambda item: str(item))}
    return str(value)


def _digest(value: Any) -> str:
    encoded = json.dumps(_canonical(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _safe_call(target: Any, name: str, *args: Any) -> tuple[bool, Any]:
    method = getattr(target, name, None)
    if not callable(method):
        return False, None
    try:
        value = method(*args)
    except Exception:
        return False, None
    return value is not False, value


def _current_color_version(item: Any) -> tuple[bool, Any]:
    getter = getattr(item, "GetCurrentVersion", None)
    if callable(getter):
        ok, value = _safe_call(item, "GetCurrentVersion")
        if not ok or not isinstance(value, dict):
            return False, None
        name = value.get("versionName")
        version_type = value.get("versionType")
        if (not isinstance(name, str) or not name
                or not isinstance(version_type, int) or isinstance(version_type, bool)
                or version_type not in (0, 1)):
            return False, None
        return True, value
    ok, value = _safe_call(item, "GetCurrentVersionName")
    return bool(ok and isinstance(value, str) and value), value


def _native_item_attestation(conn: Any, affected_ids: set[str]) -> dict[str, Any]:
    from .sdk_live_inspection import _fusion_graph_evidence

    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise ValidationError("Managed protected-state attestation requires an active timeline.")
    protected: list[dict[str, Any]] = []
    managed_facets: list[dict[str, Any]] = []
    observed_affected: set[str] = set()
    for track_type in ("video", "audio", "subtitle"):
        ok, count_value = _safe_call(timeline, "GetTrackCount", track_type)
        if not ok or not isinstance(count_value, int) or count_value < 0 or count_value > 4096:
            raise ValidationError("Managed protected-state attestation could not enumerate every track.")
        for track_index in range(1, count_value + 1):
            ok, items_value = _safe_call(timeline, "GetItemListInTrack", track_type, track_index)
            if not ok or not isinstance(items_value, list) or len(items_value) > 1_000_000:
                raise ValidationError("Managed protected-state attestation could not enumerate every timeline item.")
            for item in items_value:
                item_id = documented_unique_id(item)
                if not item_id:
                    raise ValidationError("Managed protected-state attestation found an item without durable identity.")
                properties_ok, properties = _safe_call(item, "GetProperty")
                if not properties_ok or not isinstance(properties, dict):
                    raise ValidationError("Managed protected-state attestation could not read complete item properties.")
                fusion_count_ok, fusion_count = _safe_call(item, "GetFusionCompCount")
                if not fusion_count_ok or not isinstance(fusion_count, int) or fusion_count < 0 or fusion_count > 128:
                    raise ValidationError("Managed protected-state attestation could not read Fusion composition count.")
                fusion = []
                for index in range(1, fusion_count + 1):
                    comp_ok, comp = _safe_call(item, "GetFusionCompByIndex", index)
                    if not comp_ok or comp is None:
                        raise ValidationError("Managed protected-state attestation could not read a Fusion composition.")
                    try:
                        fusion.append(_fusion_graph_evidence(comp, None))
                    except Exception as exc:
                        raise ValidationError("Managed protected-state attestation could not read a complete Fusion graph.") from exc
                color = None
                if track_type == "video":
                    graph_ok, graph = _safe_call(item, "GetNodeGraph")
                    count_ok, node_count = _safe_call(graph, "GetNumNodes") if graph_ok and graph else (False, None)
                    if not count_ok or not isinstance(node_count, int) or node_count < 0 or node_count > 4096:
                        raise ValidationError("Managed protected-state attestation could not enumerate Color nodes.")
                    nodes = []
                    for node_index in range(1, node_count + 1):
                        label_ok, label = _safe_call(graph, "GetNodeLabel", node_index)
                        lut_ok, lut = _safe_call(graph, "GetLUT", node_index)
                        tools_ok, tools = _safe_call(graph, "GetToolsInNode", node_index)
                        if (not label_ok or not isinstance(label, str)
                                or not lut_ok or not isinstance(lut, str)
                                or not tools_ok or (tools is not None and not isinstance(tools, (list, tuple, dict)))):
                            raise ValidationError("Managed protected-state attestation could not read complete Color node state.")
                        effects = [] if tools is None else (list(tools.values()) if isinstance(tools, dict) else list(tools))
                        nodes.append({"label": label, "lut": lut, "effects": effects})
                    versions = []
                    for version_type in (0, 1):
                        versions_ok, values = _safe_call(item, "GetVersionNameList", version_type)
                        if not versions_ok or not isinstance(values, (list, tuple, dict)):
                            raise ValidationError("Managed protected-state attestation could not read Color versions.")
                        versions.append(list(values.values()) if isinstance(values, dict) else list(values))
                    current_ok, current = _current_color_version(item)
                    if not current_ok:
                        raise ValidationError("Managed protected-state attestation could not read the current Color version.")
                    color = {"nodes": nodes, "versions": versions, "current": current}
                row = {"id": item_id, "trackType": track_type, "trackIndex": track_index, "properties": properties, "fusion": fusion, "color": color}
                if item_id in affected_ids:
                    observed_affected.add(item_id)
                    protected_properties = {key: value for key, value in properties.items()
                                            if any(token in str(key).lower() for token in _PROTECTED_PROPERTY_TOKENS)}
                    managed_facets.append({"slot": f"{track_type}:{track_index}", "properties": protected_properties, "fusion": fusion, "color": color})
                else:
                    protected.append(row)
    if observed_affected != affected_ids:
        raise ValidationError("Managed protected-state attestation affected identity closure is incomplete.")
    return {"protectedItems": protected, "managedProtectedFacets": managed_facets}


def _database_attestation(conn: Any, affected_ids: set[str], protected_item_ids: set[str]) -> dict[str, Any]:
    project = getattr(conn, "project", None)
    name_ok, project_name = _safe_call(project, "GetName")
    if not name_ok or not isinstance(project_name, str) or not project_name.strip():
        raise ValidationError("Managed protected-state attestation could not resolve the active project.")
    resolved = resolve_disk_project_db_path(project_name=project_name.strip())
    db_path = str(resolved.get("project_db_path") or "")
    if not db_path:
        raise ValidationError("Managed protected-state attestation requires a readable Disk Project.db.")
    settings_ok, timeline_settings = _safe_call(getattr(conn, "timeline", None), "GetSetting")
    if not settings_ok or not isinstance(timeline_settings, dict):
        raise ValidationError("Managed protected-state attestation could not read active timeline settings.")
    try:
        timeline_resolution = {
            "width": int(timeline_settings["timelineResolutionWidth"]),
            "height": int(timeline_settings["timelineResolutionHeight"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("Managed protected-state attestation could not read the active timeline resolution.") from exc
    if not all(1 <= value <= 131_072 for value in timeline_resolution.values()):
        raise ValidationError("Managed protected-state attestation returned an invalid active timeline resolution.")
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = [str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()]
        missing_color = [name for name in _COLOR_TABLES if name not in tables]
        fairlight_tables = {"Sm2Timeline", "Sm2TiTrack", "Sm2SequenceContainer", "Sm2SequenceContainer_Sm2TiTrack"}
        missing_fairlight = sorted(fairlight_tables.difference(tables))
        if missing_color or "Sm2TiItem" not in tables or "Sm2Sequence" not in tables or missing_fairlight:
            raise ValidationError("Project.db is missing a reviewed protected-family schema.", details={"missing_color_tables": missing_color})
        item_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("Sm2TiItem")').fetchall()}
        sequence_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("Sm2Sequence")').fetchall()}
        required_item = {"Sm2TiItem_id", "DbType", "EffectFiltersBA", "FieldsBlob"}
        if not required_item.issubset(item_columns) or "FieldsBlob" not in sequence_columns:
            raise ValidationError("Project.db cannot prove Fairlight, transition, and effect state from the reviewed schema.")
        timeline_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("Sm2Timeline")').fetchall()}
        track_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("Sm2TiTrack")').fetchall()}
        container_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("Sm2SequenceContainer")').fetchall()}
        track_relation_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("Sm2SequenceContainer_Sm2TiTrack")').fetchall()}
        if (not {"Name", "Sequence"}.issubset(timeline_columns)
                or not {"Sm2TiTrack_id", "Sequence", "Type", "FieldsBlob"}.issubset(track_columns)
                or not {"Sm2SequenceContainer_id", "Sm2Sequence_id"}.issubset(container_columns)
                or not {"DbOwner", "DbAssociate", "DbPropertyName", "DbIndex"}.issubset(track_relation_columns)):
            raise ValidationError("Project.db cannot prove the reviewed Fairlight track identity relation.")
        timeline_name_ok, timeline_name = _safe_call(getattr(conn, "timeline", None), "GetName")
        if not timeline_name_ok or not isinstance(timeline_name, str) or not timeline_name.strip():
            raise ValidationError("Managed protected-state attestation could not resolve the active timeline name.")
        timeline_rows = connection.execute('SELECT Sequence FROM "Sm2Timeline" WHERE Name = ?', (timeline_name.strip(),)).fetchall()
        if len(timeline_rows) != 1 or not timeline_rows[0][0]:
            raise ValidationError("Project.db cannot resolve one exact active timeline sequence for Fairlight attestation.")
        sequence_id = str(timeline_rows[0][0])
        container_ids = {str(row[0]) for row in connection.execute(
            'SELECT Sm2SequenceContainer_id FROM "Sm2SequenceContainer" WHERE Sm2Sequence_id = ?', (sequence_id,)
        ).fetchall() if row[0]}
        if not container_ids:
            raise ValidationError("Project.db cannot resolve the active timeline's Fairlight track container.")
        placeholders = ",".join("?" for _ in container_ids)
        relation_rows = connection.execute(
            f'SELECT DbOwner, DbAssociate, DbPropertyName, DbIndex FROM "Sm2SequenceContainer_Sm2TiTrack" WHERE DbOwner IN ({placeholders}) ORDER BY DbOwner, DbIndex, DbAssociate',
            tuple(sorted(container_ids)),
        ).fetchall()
        track_rows = connection.execute(
            'SELECT Sm2TiTrack_id, Type, FieldsBlob FROM "Sm2TiTrack" WHERE Sequence = ? ORDER BY Sm2TiTrack_id', (sequence_id,)
        ).fetchall()
        related_track_ids = {str(row[1]) for row in relation_rows if row[1]}
        sequence_track_ids = {str(row[0]) for row in track_rows if row[0]}
        expected_property = {0: "VideoTrackVec", 1: "AudioTrackVec", 2: "SubtitleTrackVec"}
        track_types = {str(row[0]): row[1] for row in track_rows if row[0]}
        relation_associates = [str(row[1]) for row in relation_rows if row[1]]
        relation_coordinates = [(str(row[0]), str(row[2]), row[3]) for row in relation_rows]
        vector_coordinates = [(str(row[2]), row[3]) for row in relation_rows]
        exact_relations = (len(relation_rows) == len(track_rows)
                           and all(track_type in expected_property for track_type in track_types.values())
                           and len(relation_associates) == len(set(relation_associates))
                           and len(relation_coordinates) == len(set(relation_coordinates))
                           and len(vector_coordinates) == len(set(vector_coordinates))
                           and all(isinstance(row[3], int) and not isinstance(row[3], bool) and row[3] >= 0
                                   and isinstance(row[2], str) and bool(row[2])
                                   and track_types.get(str(row[1])) in expected_property
                                   and expected_property[track_types[str(row[1])]] == row[2]
                                   for row in relation_rows))
        if (not sequence_track_ids or len(sequence_track_ids) != len(track_rows)
                or sequence_track_ids != related_track_ids or not exact_relations):
            raise ValidationError("Project.db Fairlight track rows do not match the active timeline identity relation.")
        fairlight_tracks = {
            "sequenceId": sequence_id,
            "tracks": [{"Sm2TiTrack_id": row[0], "Type": row[1], "FieldsBlob": _canonical_track_fields_blob(row[2])} for row in track_rows],
            "relations": [{"DbOwner": row[0], "DbAssociate": row[1], "DbPropertyName": row[2], "DbIndex": row[3]} for row in relation_rows],
        }
        selected = [*_COLOR_TABLES, "Sm2TiItem", "Sm2Sequence"]
        version_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("ListMgt::LmVersion")').fetchall()}
        if not {"ListMgt::LmVersion_id", "ListMgt::LmVersionTable_id", "HasCorrection", "Body"}.issubset(version_columns):
            raise ValidationError("Project.db cannot prove affected Color correction state from the reviewed schema.")
        relation_columns = {str(row[1]) for row in connection.execute('PRAGMA table_info("ListMgt::LmVersion_ListMgt::LmVersionTable")').fetchall()}
        if not {"DbOwner", "DbAssociate"}.issubset(relation_columns):
            raise ValidationError("Project.db cannot prove exact Color version ownership relations.")
        identity_columns = {
            "Sm2TiItem": {"Sm2TiItem_id"},
            "Sm2Sequence": {"Sm2Sequence_id"},
            "ListMgt::LmVersionTable": {"ListMgt::LmVersionTable_id", "Sm2TiItem_id", "pActive"},
            "ListMgt::LmVersion": {"ListMgt::LmVersion_id", "ListMgt::LmVersionTable_id"},
            "ListMgt::LmVersion_ListMgt::LmVersionTable": {"DbOwner", "DbAssociate"},
        }
        all_rows: dict[str, list[dict[str, Any]]] = {}
        for table in selected:
            columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()]
            table_rows = connection.execute(f'SELECT * FROM "{table}"').fetchall()
            normalized = []
            for raw in table_rows:
                row = dict(zip(columns, raw))
                if table == "Sm2TiItem" and row.get("DbType") != "Sm2TiTransition":
                    row = {key: row.get(key) for key in ("Sm2TiItem_id", "DbType", "EffectFiltersBA", "FieldsBlob")}
                elif table == "Sm2Sequence" and str(row.get("Sm2Sequence_id")) == sequence_id:
                    row = _canonical_active_sequence_row(row, timeline_resolution)
                normalized.append(row)
            all_rows[table] = normalized
        closure = set(affected_ids)
        excluded: set[tuple[str, int]] = set()
        changed = True
        while changed:
            changed = False
            for table, table_rows in all_rows.items():
                for index, row in enumerate(table_rows):
                    identity = (table, index)
                    if identity in excluded:
                        continue
                    strings = {value for value in row.values() if isinstance(value, str) and value}
                    if not strings.intersection(closure):
                        continue
                    if strings.intersection(protected_item_ids):
                        raise ValidationError("Managed protected-state database closure intersects a protected timeline item.")
                    excluded.add(identity)
                    for column, value in row.items():
                        if isinstance(value, str) and value and column in identity_columns[table]:
                            closure.add(value)
                    changed = True
        rows = {table: sorted((_canonical(row) for index, row in enumerate(table_rows) if (table, index) not in excluded),
                              key=lambda row: json.dumps(row, sort_keys=True, default=str)) for table, table_rows in all_rows.items()}
        affected_rows = []
        affected_protected_rows = []
        for table, table_rows in all_rows.items():
            for index, row in enumerate(table_rows):
                if (table, index) not in excluded:
                    continue
                affected_rows.append({"table": table, "row": row})
                if table == "Sm2TiItem" and (row.get("DbType") == "Sm2TiTransition"
                                               or row.get("EffectFiltersBA") not in (None, b"", "") ):
                    affected_protected_rows.append({"table": table, "row": row})
                elif table == "Sm2Sequence":
                    affected_protected_rows.append({"table": table, "row": row})
                elif table == "ListMgt::LmVersion" and (row.get("HasCorrection") not in (None, False, 0, "0", "")
                                                         or row.get("Body") not in (None, b"", "")):
                    affected_protected_rows.append({"table": table, "row": row})
        key = lambda value: json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"))
        return {"schemaTables": [*selected, *sorted(fairlight_tables)], "protectedRows": rows,
                "fairlightTracks": fairlight_tracks,
                "affectedRows": sorted(affected_rows, key=key),
                "affectedProtectedRows": sorted(affected_protected_rows, key=key)}
    finally:
        connection.close()


def attest_managed_protected_state(
    conn: Any,
    *,
    affected_native_ids: list[str],
    retained_database_native_ids: list[str] | None = None,
) -> dict[str, Any]:
    if len(set(affected_native_ids)) != len(affected_native_ids):
        raise ValidationError("Managed protected-state attestation requires a unique affected identity closure.")
    affected = set(affected_native_ids)
    retained_database = set(retained_database_native_ids or affected_native_ids)
    if not affected.issubset(retained_database):
        raise ValidationError("Managed protected-state retained database closure omitted a live affected identity.")
    native = _native_item_attestation(conn, affected)
    protected_item_ids = {str(row.get("id")) for row in native.get("protectedItems", []) if row.get("id")}
    database = _database_attestation(conn, retained_database, protected_item_ids)
    affected_native_state = native.pop("managedProtectedFacets")
    affected_db_rows = database.pop("affectedProtectedRows")
    affected_all_db_rows = database.pop("affectedRows")
    protected_value = {"native": native, "database": database}
    def _color_non_default(color: Any) -> bool:
        if not isinstance(color, dict):
            return False
        nodes = color.get("nodes") or []
        if len(nodes) != 1 or any(node.get("lut") or node.get("effects")
                                  or (node.get("label") and not re.fullmatch(r"(?:Corrector|Node)\s*1", str(node.get("label")), re.IGNORECASE))
                                  for node in nodes):
            return True
        return any(len(values) > 1 for values in color.get("versions") or [] if isinstance(values, list))

    def _property_non_default(key: Any, value: Any) -> bool:
        normalized = str(key).lower()
        if "opacity" in normalized:
            return value not in (None, 1, 100, "1", "100", "100.0")
        if "composite" in normalized:
            return value not in (None, False, 0, "0", "Normal", "normal")
        return value not in (None, False, 0, "", [], {})

    affected_empty = not any(entry.get("fusion") or _color_non_default(entry.get("color"))
                             or any(_property_non_default(key, value) for key, value in entry.get("properties", {}).items())
                             for entry in affected_native_state) and not affected_db_rows
    return {
        "protected_state_digest": _digest(protected_value),
        "affected_state_digest": _digest({"native": affected_native_state, "database": affected_all_db_rows}),
        "affected_native_ids": sorted(affected),
        "affected_protected_state_empty": affected_empty,
        "coverage": {
            "fusion": True, "color": True, "fairlight": True,
            "transitions": True, "effects": True, "captions": True,
        },
        "coverage_evidence": {
            "fusion": "timeline-item Fusion graph nodes, inputs, connections, expressions, and keyframes",
            "color": "timeline-item Color node graphs, LUTs, effects, local/remote versions, and active version",
            "fairlight": "reviewed Project.db Sm2TiTrack identity-linked FieldsBlob, Sm2Sequence protected model bytes with exact edit-bookkeeping normalization, and Sm2TiItem EffectFiltersBA payloads",
            "transitions": "reviewed Project.db Sm2TiTransition rows",
            "effects": "timeline-item properties plus reviewed Sm2TiItem EffectFiltersBA payloads",
            "captions": "complete native subtitle-track item inventory and properties",
        },
    }
