"""Verified Disk-project fallback for attaching a Fusion composition."""

from __future__ import annotations

import base64
import hashlib
import re
import time
import uuid
import zlib
from typing import Any, Callable

from ..errors import APICallFailed, ValidationError
from . import db_session, db_timeline_rows, db_timeline_selection
from .transition_db import build_fusion_composition_fields_blob


_SEED_ITEM_ID = "f8397cc9-0622-44fd-abcc-1352c1223664"
_SEED_SHA256 = "0119714d620c7d4d8679c06915d65f42d931cb210c8a3d339a2a0237eec74220"
_SEED_B64 = (
    "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"
)
_MINIMAL_GRAPH = (
    b'{ Background1 = Background { Inputs = { GlobalOut = Input { Value = 119, }, '
    b'Width = Input { Value = 1920, }, Height = Input { Value = 1080, }, '
    b'UseFrameFormatSettings = Input { Value = 1, }, }, }, '
    b'MediaOut1 = MediaOut { Inputs = { Index = Input { Value = "0", }, '
    b'Input = Input { SourceOp = "Background1", Source = "Output", }, }, }, }\0'
)


def _seed_blob() -> bytes:
    blob = base64.b64decode(_SEED_B64, validate=True)
    if hashlib.sha256(blob).hexdigest() != _SEED_SHA256:
        raise APICallFailed("Bundled Fusion composition seed failed its integrity check.")
    return blob


def rebuild_composition_blob(
    seed_blob: bytes,
    *,
    old_item_id: str,
    new_item_id: str,
    transform_inner: Callable[[bytes], bytes] | None = None,
) -> bytes:
    """Patch one audited composition container while preserving its binary envelope."""

    try:
        outer = bytearray(zlib.decompress(seed_blob[4:]))
    except Exception as exc:
        raise APICallFailed("Fusion composition seed could not be decompressed.") from exc
    old_id = old_item_id.encode("utf-8")
    if bytes(outer).count(old_id) != 1:
        raise APICallFailed("Fusion composition seed does not contain one exact item identity.")
    outer = bytearray(bytes(outer).replace(old_id, new_item_id.encode("utf-8")))

    inner_offset = -1
    inner = None
    for match in re.finditer(b"\x78\xda|\x78\x9c|\x78\x01", bytes(outer)):
        try:
            candidate = zlib.decompress(bytes(outer)[match.start() :])
        except Exception:
            continue
        inner_offset = match.start()
        inner = candidate
    if inner is None or inner_offset < 4:
        raise APICallFailed("Fusion composition seed has no nested graph payload.")
    replacement = transform_inner(inner) if transform_inner is not None else inner
    if not isinstance(replacement, bytes) or not replacement.endswith(b"\0"):
        raise APICallFailed("Fusion composition graph payload is malformed.")

    compressed_inner = zlib.compress(replacement, 9)
    rebuilt = bytearray(bytes(outer[: inner_offset - 4]) + len(replacement).to_bytes(4, "little") + compressed_inner)
    comp_offset = bytes(rebuilt).find(b"Composition {")
    if comp_offset < 4:
        raise APICallFailed("Fusion composition seed has no Composition field.")
    rebuilt[comp_offset - 4 : comp_offset] = (len(rebuilt) - comp_offset).to_bytes(4, "big")
    return len(rebuilt).to_bytes(4, "big") + zlib.compress(bytes(rebuilt))


def _timeline_topology(conn: Any) -> list[tuple[str, int, str, int, int]]:
    rows: list[tuple[str, int, str, int, int]] = []
    for track_type in ("video", "audio"):
        for track_index in range(1, int(conn.timeline.GetTrackCount(track_type) or 0) + 1):
            for item in conn.timeline.GetItemListInTrack(track_type, track_index) or []:
                rows.append((track_type, track_index, str(item.GetName() or ""), int(item.GetStart()), int(item.GetEnd())))
    return rows


def attach_fusion_composition_via_project_db(conn: Any, *, item_ref: db_timeline_selection.LiveItemRef) -> dict[str, Any]:
    """Attach one seed composition through the hardened Disk-project transaction."""

    timeline_name = str(conn.timeline.GetName() or "")
    if not timeline_name:
        raise ValidationError("Fusion DB fallback requires an exact active timeline.")
    topology_before = _timeline_topology(conn)

    def writer(_connection: Any, cursor: Any, _session: Any) -> dict[str, Any]:
        row = db_timeline_rows.find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
            require_timeline_name=True,
        )
        item_id = str(row["Sm2TiItem_id"])
        if item_ref.item_id and item_ref.item_id != item_id:
            raise ValidationError("Fusion DB fallback target identity changed before mutation.")
        existing = cursor.execute(
            "SELECT Sm2TiCompositionTable_id FROM Sm2TiCompositionTable WHERE Sm2TiItem_id = ?",
            (item_id,),
        ).fetchall()
        if existing or row.get("CompositionTable"):
            raise ValidationError("Fusion DB fallback target already has a composition.")
        composition_id = str(uuid.uuid4())
        saved_time = int(time.time())
        composition_blob = rebuild_composition_blob(
            _seed_blob(),
            old_item_id=_SEED_ITEM_ID,
            new_item_id=item_id,
            transform_inner=lambda _inner: _MINIMAL_GRAPH,
        )
        db_timeline_rows.insert_row(
            cursor,
            "Sm2TiCompositionTable",
            {
                "Sm2TiCompositionTable_id": composition_id,
                "DbType": "Sm2TiCompositionTable",
                "FieldsBlob": build_fusion_composition_fields_blob(saved_time),
                "DbSavedTime": saved_time,
                "CompositionBA": composition_blob,
                "ActiveCompositionIdx": 0,
                "Sm2TiItem_id": item_id,
                "Sm2MpMedia_id": None,
                "Sm2CompositionTableManager_id": None,
            },
        )
        db_timeline_rows.update_row(
            cursor, "Sm2TiItem", "Sm2TiItem_id", item_id, {"CompositionTable": composition_id},
        )
        return {
            "item_id": item_id,
            "composition_id": composition_id,
            "timeline_name": timeline_name,
            "topology_before": topology_before,
        }

    def verifier(fresh_conn: Any, result: dict[str, Any], _session: Any) -> dict[str, Any]:
        matches = [
            row for row in db_timeline_selection._read_live_items(fresh_conn, track_type="video")
            if row.item_id == result["item_id"]
        ]
        if len(matches) != 1:
            raise APICallFailed("Fusion DB fallback could not read back the exact target item.")
        live_item = fresh_conn.timeline.GetItemListInTrack("video", matches[0].track_index) or []
        native = next(
            (item for item in live_item if str(getattr(item, "GetUniqueId", lambda: "")() or "") == result["item_id"]),
            None,
        )
        if native is None or int(native.GetFusionCompCount() or 0) != 1:
            raise APICallFailed("DaVinci Resolve did not accept the attached Fusion composition.")
        comp = native.GetFusionCompByIndex(1)
        tools = comp.GetToolList(False) if comp is not None else None
        tool_values = list(tools.values()) if isinstance(tools, dict) else list(tools or [])
        tool_types = {
            str((tool.GetAttrs() or {}).get("TOOLS_RegID") or "") for tool in tool_values
            if hasattr(tool, "GetAttrs")
        }
        if "MediaOut" not in tool_types or len(tool_values) < 2:
            raise APICallFailed("DaVinci Resolve readback found an incomplete Fusion seed graph.")
        if _timeline_topology(fresh_conn) != result["topology_before"]:
            raise APICallFailed("Fusion DB fallback changed protected timeline topology.")
        return {
            "status": "verified",
            "item_id": result["item_id"],
            "composition_id": result["composition_id"],
            "composition_count": 1,
            "tool_count": len(tool_values),
            "protected_timeline_topology": "preserved",
        }

    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fusion composition attach",
        writer=writer,
        verifier=verifier,
        save_project=True,
        allow_project_name_inference=True,
        require_verified=True,
    )
