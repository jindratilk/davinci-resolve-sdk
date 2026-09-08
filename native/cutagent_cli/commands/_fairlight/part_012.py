"""Fairlight ClipFX verification helpers and AI read command."""

from __future__ import annotations

def _get_audio_clip_id(conn):
    """Get the first audio clip ID from current timeline."""
    cursor = conn.disk_db_cursor()
    return _get_audio_clip_id_from_cursor(cursor)


def _get_audio_clip_id_from_cursor(cursor):
    """Get the first audio clip ID from a Project.db cursor."""
    row = cursor.execute(
        "SELECT Sm2TiItem_id FROM Sm2TiItem WHERE DbType='Sm2TiAudioClip'"
    ).fetchone()
    if not row:
        raise ReadinessFailed(
            "No audio clip found in timeline.",
            details={
                "precondition": "timeline_contains_audio_clip",
            },
        )
    return row[0] if isinstance(row, tuple) else row["Sm2TiItem_id"]


def _read_clip_fx_state(project_db_path: str, clip_id: str):
    from ..core.audio_clip_fx import read_clip_fx_from_db

    connection = sqlite3.connect(project_db_path)
    connection.row_factory = sqlite3.Row
    try:
        return read_clip_fx_from_db(connection.cursor(), clip_id)
    finally:
        connection.close()


def _raise_failed_verification(message: str, *, checks: list[dict[str, Any]], details: dict[str, Any]) -> None:
    failed = [check for check in checks if not check.get("ok")]
    if failed:
        raise APICallFailed(
            message,
            details={
                **details,
                "verification": {
                    "status": "failed",
                    "checks": checks,
                },
            },
        )


def _verify_clip_fx_params(
    *,
    project_db_path: str,
    clip_id: str,
    plugin_id: str,
    expected_params: dict[str, float],
    feature: str,
) -> dict[str, Any]:
    state = _read_clip_fx_state(project_db_path, clip_id)
    checks: list[dict[str, Any]] = []
    for param_name, expected in expected_params.items():
        actual = state.get_param(plugin_id, param_name) if state else None
        checks.append(
            {
                "name": param_name,
                "expected": expected,
                "actual": actual,
                "ok": actual is not None and abs(float(actual) - float(expected)) <= 0.0001,
            }
        )
    _raise_failed_verification(
        f"Fairlight {feature} DB write did not match readback.",
        checks=checks,
        details={"feature": feature, "clip_id": clip_id, "project_db_path": project_db_path},
    )
    return {"status": "verified", "checks": checks}


def _verify_clip_fx_removed(
    *,
    project_db_path: str,
    clip_id: str,
    plugin_id: str,
    feature: str,
) -> dict[str, Any]:
    state = _read_clip_fx_state(project_db_path, clip_id)
    remaining_plugins = _clip_fx_available_plugins(state)
    still_present = any(plugin.get("plugin_id") == plugin_id for plugin in remaining_plugins)
    checks = [
        {
            "name": "clip_fx_plugin_removed",
            "expected_absent_plugin_id": plugin_id,
            "actual_remaining_plugins": remaining_plugins,
            "ok": not still_present,
        }
    ]
    _raise_failed_verification(
        f"Fairlight {feature} FX removal did not match readback.",
        checks=checks,
        details={"feature": feature, "clip_id": clip_id, "project_db_path": project_db_path},
    )
    return {"status": "verified", "checks": checks, "remaining_clip_fx_plugins": remaining_plugins}


def _verify_clip_fx_present(
    *,
    project_db_path: str,
    clip_id: str,
    plugin_id: str,
    feature: str,
) -> dict[str, Any]:
    state = _read_clip_fx_state(project_db_path, clip_id)
    plugins = _clip_fx_available_plugins(state)
    present = any(plugin.get("plugin_id") == plugin_id for plugin in plugins)
    checks = [
        {
            "name": "clip_fx_plugin_present",
            "expected_plugin_id": plugin_id,
            "actual_plugins": plugins,
            "ok": present,
        }
    ]
    _raise_failed_verification(
        f"Fairlight {feature} FX add did not match readback.",
        checks=checks,
        details={"feature": feature, "clip_id": clip_id, "project_db_path": project_db_path},
    )
    return {"status": "verified", "checks": checks, "clip_fx_plugins": plugins}


def _verify_eq_payload(
    *,
    project_db_path: str,
    audio_item_id: str,
    expected_payload: bytes,
) -> dict[str, Any]:
    connection = sqlite3.connect(project_db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT EffectFiltersBA FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
            (audio_item_id,),
        ).fetchone()
    finally:
        connection.close()
    actual_payload = bytes(row["EffectFiltersBA"] or b"") if row else b""
    checks = [
        {
            "name": "effect_filters_payload",
            "expected_length": len(expected_payload),
            "actual_length": len(actual_payload),
            "ok": actual_payload == expected_payload,
        }
    ]
    _raise_failed_verification(
        "Fairlight EQ DB write did not match readback.",
        checks=checks,
        details={"audio_item_id": audio_item_id, "project_db_path": project_db_path},
    )
    return {"status": "verified", "checks": checks}


@ai_app.command("read")
@handle_errors
def ai_read(
    clip: str | None = typer.Option(None, "--clip", help="Timeline audio clip name or id to inspect; defaults to the first current-timeline audio clip"),
):
    """Read all AI audio feature settings from the current clip."""
    from ..core.audio_clip_fx import read_clip_fx_from_db

    enforce_mutation_policy("fairlight.ai_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        preflight_parts = ["cutagent", "fairlight", "ai", "read"]
        if clip is not None:
            preflight_parts.extend(["--clip", str(clip)])
        preflight_parts.append("--json")
        output(
            {
                "action": "fairlight.ai.read",
                "dry_run": True,
                "runtime_read_called": False,
                "target": {
                    "kind": "audio_clip",
                    "clip": clip,
                    "default": "first_current_timeline_audio_clip" if not clip else None,
                },
                "route": "db_workaround",
                "db_readback": {
                    "table": "Sm2TiItem",
                    "column": "FieldsBlob",
                    "payload": "FL::ClipFX",
                    "storage": "zstd_zlib_clip_fx_payload",
                },
                "read_scope": "clip_fx_ai_audio_features",
                "requires_current_audio_clip": True,
                "preflight_command": " ".join(shlex.quote(part) for part in preflight_parts),
            },
            title="AI Audio Features Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    cursor = conn.disk_db_cursor()
    clip_row = _resolve_fairlight_clip_fx_row(cursor, conn=conn, clip_selector=clip)
    clip_id = str(clip_row.get("Sm2TiItem_id") or "")
    state = read_clip_fx_from_db(cursor, clip_id)
    native_voice_isolation = None
    try:
        native_voice_isolation = clip_ops.get_voice_isolation(conn, clip_id)
    except (APICallFailed, CapabilityNegotiationFailed, ClipNotFound, ValidationError, AttributeError):
        # Other AI features remain readable from FL::ClipFX when this native
        # TimelineItem state is unavailable. Voice Isolation mutations require
        # the native getter, so their SDK verification still fails closed.
        pass
    target = {
        "kind": "audio_clip",
        "clip": clip,
        "clip_id": clip_id,
        "name": clip_row.get("Name"),
        "track_index": clip_row.get("track_index"),
    }
    db_readback = {
        "table": "Sm2TiItem",
        "column": "FieldsBlob",
        "payload": "FL::ClipFX",
        "storage": "zstd_zlib_clip_fx_payload",
    }
    if state:
        data = state.to_dict()
        if native_voice_isolation is not None:
            data["native_voice_isolation"] = native_voice_isolation
        data.update(
            {
                "action": "fairlight.ai.read",
                "route": "db_workaround",
                "target": target,
                "found": bool(getattr(state, "plugins", []) or []),
                "db_readback": db_readback,
            }
        )
        output(data, title="AI Audio Features")
    else:
        data = {
                "action": "fairlight.ai.read",
                "route": "db_workaround",
                "target": target,
                "found": False,
                "plugins": [],
                "status": "No AI audio features found on clip",
                "db_readback": db_readback,
            }
        if native_voice_isolation is not None:
            data["native_voice_isolation"] = native_voice_isolation
            data["found"] = bool(native_voice_isolation.get("isEnabled"))
        output(data, title="AI Audio Features")
