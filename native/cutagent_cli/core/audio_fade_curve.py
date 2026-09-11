"""Lossless audio fade control-point edits for local Disk projects.

99 and 100 are independently stored native fade-in/out control points in the
124 audio-mix effect. Coordinates are native values, not normalized easing
percentages. An absent point selects the native linear envelope.
"""

from __future__ import annotations

import math
import sqlite3
import struct
from . import (
    clip_effects_db as effects,
    db_session,
    db_timeline_rows,
    db_timeline_selection,
)
from ..errors import ValidationError, APICallFailed


def validate_point(point):
    if point is None:
        return None
    if not isinstance(point, dict) or set(point) != {"x", "y"}:
        raise ValidationError(
            "Fade curve requires x and y control-point values, or null for linear."
        )
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        for v in point.values()
    ):
        raise ValidationError("Fade curve control-point values must be finite numbers.")
    return {k: float(point[k]) for k in ("x", "y")}


def _parameter(direction):
    if direction not in ("in", "out"):
        raise ValidationError("Fade direction must be in or out.")
    return 99 if direction == "in" else 100


def read_curve(blob, direction):
    param = _parameter(direction)
    found = []
    for entry in effects.split_packed_blob_chain(blob):
        proto = effects._parse_wire_fields(effects._effect_proto(entry))
        if proto is None:
            raise ValidationError("Audio effect data cannot be decoded without loss.")
        for top in proto:
            if (
                top.number != 1
                or top.wire_type != 2
                or effects._effect_message_id(top.value) != 124
            ):
                continue
            for field in effects._parse_wire_fields(top.value) or []:
                if (
                    field.number == 9
                    and field.wire_type == 2
                    and effects._audio_param_id(field.value) == param
                ):
                    fields = effects._parse_wire_fields(field.value)
                    value = [
                        f.value
                        for f in fields or []
                        if f.number == 3 and f.wire_type == 2
                    ]
                    if (
                        len(value) != 1
                        or len(value[0]) != 20
                        or value[0][:4] != b"\x0a\x12\x3a\x10"
                    ):
                        raise ValidationError(
                            "Audio fade curve has an unsupported control-point encoding."
                        )
                    x, y = struct.unpack(">dd", value[0][4:])
                    found.append(validate_point({"x": x, "y": y}))
    if len(found) > 1:
        raise ValidationError(
            "Audio fade curve is ambiguous: duplicate control points."
        )
    return found[0] if found else None


def patch_curve(blob, direction, point):
    point = validate_point(point)
    param = _parameter(direction)
    read_curve(
        blob, direction
    )  # Reject ambiguous/unknown encodings before replacing anything.
    if read_curve(blob, direction) == point:
        return blob
    replacement = None
    if point is not None:
        value = b"\x0a\x12\x3a\x10" + struct.pack(">dd", point["x"], point["y"])
        replacement = effects._encode_length_delimited_field(
            9,
            b"\x08"
            + effects._encode_varint(param)
            + effects._encode_length_delimited_field(3, value),
        )
    output = []
    mixes = 0
    for entry in effects.split_packed_blob_chain(blob):
        fields = effects._parse_wire_fields(effects._effect_proto(entry))
        if fields is None:
            raise ValidationError("Audio effect data cannot be decoded without loss.")
        top = []
        changed = False
        for field in fields:
            if (
                field.number == 1
                and field.wire_type == 2
                and effects._effect_message_id(field.value) == 124
            ):
                mixes += 1
                mix = effects._parse_wire_fields(field.value)
                if mix is None:
                    raise ValidationError("Audio mix data is malformed.")
                parts = []
                inserted = False
                for p in mix:
                    if (
                        p.number == 9
                        and p.wire_type == 2
                        and effects._audio_param_id(p.value) == param
                    ):
                        if replacement is not None:
                            parts.append(replacement)
                        inserted = True
                    else:
                        parts.append(p.raw)
                if replacement is not None and not inserted:
                    parts.append(replacement)
                top.append(effects._encode_length_delimited_field(1, b"".join(parts)))
                changed = True
            else:
                top.append(field.raw)
        output.append(
            effects._repack_effect_proto(entry, b"".join(top)) if changed else entry
        )
    if mixes != 1:
        raise ValidationError(
            "An exact existing audio mix is required to edit the fade curve."
        )
    return effects.join_packed_blob_chain(output)


def _target(conn, item_id):
    refs = [
        r
        for r in db_timeline_selection._read_live_items(conn, track_type="audio")
        if item_id in r.aliases
    ]
    if len(refs) != 1:
        raise ValidationError("Fade curve requires one exact audio timeline item.")
    return refs[0]


def _row(cur, ref, name):
    return db_timeline_rows.find_ti_item_row(
        cur, item=ref, db_type="Sm2TiAudioClip", timeline_name=name
    )


def read(conn, item_id, direction):
    ref = _target(conn, item_id)
    info = db_session.resolve_current_disk_project_db(
        conn, allow_project_name_inference=True
    )
    with sqlite3.connect(
        "file:" + str(info["project_db_path"]) + "?mode=ro", uri=True
    ) as db:
        db.row_factory = sqlite3.Row
        row = _row(db.cursor(), ref, conn.timeline.GetName())
        return {
            "item_id": item_id,
            "direction": direction,
            "control_point": read_curve(row.get("EffectFiltersBA"), direction),
        }


def set_curve(conn, item_id, direction, point):
    point = validate_point(point)
    _parameter(direction)
    ref = _target(conn, item_id)
    name = conn.timeline.GetName()
    project_id = conn.project.GetUniqueId()
    timeline_id = conn.timeline.GetUniqueId()
    items = [
        i
        for i in conn.timeline.GetItemListInTrack("audio", ref.track_index)
        if i.GetUniqueId() == item_id
    ]
    if len(items) != 1:
        raise ValidationError("Fade curve target identity is unavailable.")
    before_fades = items[0].GetFades()
    edge = "FadeIn" if direction == "in" else "FadeOut"
    if (
        not isinstance(before_fades, dict)
        or not isinstance(before_fades.get(edge), (int, float))
        or before_fades[edge] <= 0
    ):
        raise ValidationError("Set a positive fade duration before changing its curve.")

    # Flush pending GUI edits before comparing the persisted native point. A
    # no-op must not close/reopen the project and invalidate unrelated handles.
    if not conn.project_manager.SaveProject():
        raise APICallFailed("Could not save the current audio fade state.")
    current = read(conn, item_id, direction)["control_point"]
    if current == point:
        from ..output import set_verification_status

        set_verification_status("verified")
        return {
            "item_id": item_id,
            "direction": direction,
            "before": current,
            "after": point,
            "changed": False,
            "verification": {
                "status": "verified",
                "checks": [{"name": "saved_curve_already_matches", "ok": True}],
            },
        }

    def writer(db, cur, session):
        row = _row(cur, ref, name)
        before = row.get("EffectFiltersBA")
        after = patch_curve(before, direction, point)
        db_timeline_rows.update_row(
            cur,
            "Sm2TiItem",
            "Sm2TiItem_id",
            row["Sm2TiItem_id"],
            {"EffectFiltersBA": after},
        )
        return {
            "item_id": item_id,
            "direction": direction,
            "before": read_curve(before, direction),
            "after": point,
            "changed": after != before,
            "db_item_id": row["Sm2TiItem_id"],
            "expected_blob": bytes(after).hex(),
        }

    def verifier(fresh, result, session):
        if (
            fresh.project.GetUniqueId() != project_id
            or fresh.timeline.GetUniqueId() != timeline_id
        ):
            raise APICallFailed(
                "DaVinci Resolve did not restore the fade curve target."
            )
        found = [
            i
            for i in fresh.timeline.GetItemListInTrack("audio", ref.track_index)
            if i.GetUniqueId() == item_id
        ]
        if len(found) != 1 or found[0].GetFades() != before_fades:
            raise APICallFailed(
                "Fade curve edit changed the clip identity or fade durations."
            )
        # Save again so the check sees the state accepted by the reopened application.
        if not fresh.project_manager.SaveProject():
            raise APICallFailed("Could not save the reopened fade curve state.")
        with sqlite3.connect(session.project_db_path) as db:
            raw = db.execute(
                "SELECT EffectFiltersBA FROM Sm2TiItem WHERE Sm2TiItem_id=?",
                (result["db_item_id"],),
            ).fetchone()
        if raw is None or bytes(raw[0]).hex() != result["expected_blob"]:
            raise APICallFailed(
                "DaVinci Resolve did not preserve the requested curve and surrounding effects."
            )
        return {
            "status": "verified",
            "checks": [
                {
                    "name": "curve_and_protected_effects_preserved_after_reopen",
                    "ok": True,
                }
            ],
        }

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Audio fade curve",
        writer=writer,
        verifier=verifier,
        require_verified=True,
    )
    result.pop("expected_blob", None)
    result.pop("db_item_id", None)
    return result


def observe_curve(blob, direction):
    try:
        return {"controlPoint": read_curve(blob, direction)}
    except ValidationError:
        return None
