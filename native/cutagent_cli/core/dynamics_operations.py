"""Active timeline binding and reopen verification for native track dynamics."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..errors import APICallFailed, ValidationError
from . import db_session, dynamics_db, fairlight_ops


def _read_bound(db_path, *, timeline_name, track):
    with sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True) as connection:
        cursor = connection.cursor()
        sequence = fairlight_ops._fetch_timeline_sequence(cursor, timeline_name)
        return dynamics_db.read_dynamics_from_cursor(cursor, sequence_id=sequence, track=track)


def _timeline_name(conn):
    name = fairlight_ops._timeline_name(conn)
    if not name:
        raise ValidationError("Fairlight dynamics requires an active timeline.")
    return name


def read_active_dynamics(conn, *, track=1):
    return _read_bound(conn.disk_db_path(), timeline_name=_timeline_name(conn), track=track)


def set_active_dynamics(conn, *, params, track=1, action="fairlight.dynamics.set"):
    # Validate before saving or closing a project. Values in readback use native
    # quantization, so compare with the encoded request rather than its float.
    params = dynamics_db.normalize_params(params)
    expected = {name: dynamics_db._decode_value(name, dynamics_db._encode_value(name, value))
                for name, value in params.items()}
    if not expected:
        raise ValidationError("At least one dynamics parameter is required.")
    timeline_name = _timeline_name(conn)
    initial = read_active_dynamics(conn, track=track)
    bound = {}

    def validate(fresh_conn, session):
        if _timeline_name(fresh_conn) != timeline_name:
            raise ValidationError("Active timeline changed before the dynamics mutation.")
        current = _read_bound(session.project_db_path, timeline_name=timeline_name, track=track)
        if current["sequence_id"] != initial["sequence_id"] or current["track"] != initial["track"]:
            raise ValidationError("Audio track binding changed before the dynamics mutation.")
        bound.update(current)

    def writer(_connection, cursor, _session):
        sequence = fairlight_ops._fetch_timeline_sequence(cursor, timeline_name)
        before = dynamics_db.read_dynamics_from_cursor(cursor, sequence_id=sequence, track=track)
        if before != bound:
            raise ValidationError("Audio track dynamics changed after preflight.")
        result = dynamics_db.write_dynamics_params_with_cursor(
            cursor, params, sequence_id=sequence, track=track,
            expected_track_id=initial["track"]["track_id"],
        )
        return {"action": action, "timeline_name": timeline_name, "requested": expected, **result}

    def verifier(fresh_conn, _result, session):
        if _timeline_name(fresh_conn) != timeline_name:
            raise APICallFailed("DaVinci Resolve did not restore the dynamics timeline.")
        readback = _read_bound(session.project_db_path, timeline_name=timeline_name, track=track)
        checks = [{"name": "sequence_id", "ok": readback["sequence_id"] == initial["sequence_id"]},
                  {"name": "track", "ok": readback["track"] == initial["track"]}]
        for name in dynamics_db.PARAM_IDS:
            value = expected.get(name, bound[name])
            actual = readback[name]
            checks.append({"name": name, "expected": value, "actual": actual, "ok": actual == value})
        if not all(check["ok"] for check in checks):
            raise APICallFailed("Fairlight dynamics did not match readback after project reopen.",
                                details={"checks": checks, "readback": readback}, recoverability="manual")
        return {"status": "verified", "checks": checks, "readback": readback}

    return db_session.execute_sqlite_disk_db_mutation(
        conn, context="Fairlight Dynamics DB write", writer=writer, verifier=verifier,
        pre_close_validator=validate, allow_project_name_inference=True,
    )
