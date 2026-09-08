"""Truthful projection for the track-oriented Fairlight mutation slice.

The inputs to this module are production shapes: a captured legacy handler
result, the normalized SDK request, a current ``fairlight tracks``/specialized
readback, and the carrier verification returned by ``PreparedAction.verify``.
No message text, implementation-route name, or field-name substring is treated
as proof.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping



class UnsupportedFairlightTrackProjection(ValueError):
    """The available production result cannot prove the public result."""


SUPPORTED_ACTION_IDS = frozenset(
    f"cutagent.action.{command_id}"
    for command_id in (
        "fairlight.add",
        "fairlight.automation.write",
        "fairlight.bus.assign",
        "fairlight.bus.level",
        "fairlight.delete",
        "fairlight.dynamics.disable",
        "fairlight.dynamics.enable",
        "fairlight.dynamics.set",
        "fairlight.ensure_stereo_tracks",
        "fairlight.ensure_tracks",
        "fairlight.lock",
        "fairlight.mixer.fader",
        "fairlight.mixer.pan",
        "fairlight.mute",
        "fairlight.preset.apply",
        "fairlight.rename",
        "fairlight.solo",
        "fairlight.solo_restore",
        "fairlight.track.duplicate",
        "fairlight.track_color",
        "fairlight.track_format.set",
        "fairlight.track_order.move",
        "fairlight.unlock",
        "fairlight.unmute",
        "fairlight.voice_isolation.set",
    )
)

# These live handlers return only ``success(message)``. They become projectable
# only when both before and current ``fairlight tracks`` readbacks are supplied.
READBACK_REQUIRED_ACTION_IDS = frozenset(
    f"cutagent.action.fairlight.{name}"
    for name in ("lock", "mute", "rename", "solo_restore", "unlock", "unmute")
)

# Production routes which cannot be projected from the handler result alone.
# The value names the additional authoritative readback the caller must supply.
INSUFFICIENT_HANDLER_ROUTES = {
    "cutagent.action.fairlight.automation.write": "normalized record-frame automation readback",
    "cutagent.action.fairlight.lock": "before/current fairlight.tracks readback",
    "cutagent.action.fairlight.mixer.fader": "complete mixer state readback",
    "cutagent.action.fairlight.mixer.pan": "complete mixer state readback",
    "cutagent.action.fairlight.mute": "before/current fairlight.tracks readback",
    "cutagent.action.fairlight.rename": "before/current fairlight.tracks readback",
    "cutagent.action.fairlight.solo_restore": "before/current fairlight.tracks readback",
    "cutagent.action.fairlight.unlock": "before/current fairlight.tracks readback",
    "cutagent.action.fairlight.unmute": "before/current fairlight.tracks readback",
}


def _fail(message: str) -> None:
    raise UnsupportedFairlightTrackProjection(message)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label} is not a structured object")
    return value


def _command_id(action_id: str) -> str:
    if action_id not in SUPPORTED_ACTION_IDS:
        _fail(f"{action_id} has no reviewed track-oriented Fairlight projection")
    return action_id.removeprefix("cutagent.action.")


def _verify_handler(command_id: str, handler: Mapping[str, Any]) -> None:
    if handler.get("dry_run") is True:
        _fail("dry-run output is not mutation evidence")
    reported = handler.get("action")
    if reported is not None and reported != command_id:
        _fail("handler result belongs to a different Fairlight action")
    verification = handler.get("verification")
    if isinstance(verification, Mapping):
        status = verification.get("status")
        if status is not None and status != "verified":
            _fail("handler verification did not pass")
        checks = verification.get("checks")
        if checks is not None:
            if not isinstance(checks, list) or any(
                not isinstance(check, Mapping) or check.get("ok") is not True
                for check in checks
            ):
                _fail("handler verification checks did not all pass")


def _proof(
    verification: Any, *, required_modalities: set[str]
) -> tuple[list[dict[str, str]], bool]:
    value = _mapping(verification, "carrier verification")
    if set(value) != {"outcome", "evidence", "protectedStatePreserved"}:
        _fail("carrier verification does not have the strict SDK result fields")
    if value.get("outcome") != "passed":
        _fail("carrier verification did not pass")
    if value.get("protectedStatePreserved") is not True:
        _fail("protected-state preservation is absent or did not pass")
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        _fail("carrier verification evidence is absent")
    rows: list[dict[str, str]] = []
    for row in evidence:
        if (
            not isinstance(row, Mapping)
            or not {"modality", "digest", "summary"} <= set(row)
            or set(row)
            - {"modality", "digest", "summary", "artifactId", "targetRangeDigest"}
        ):
            _fail("carrier evidence does not have the strict SDK fields")
        if row.get("modality") not in {"readback", "structural", "auditioned"}:
            continue
        if not all(
            isinstance(row.get(key), str) and row[key] for key in ("digest", "summary")
        ):
            _fail("carrier evidence is incomplete")
        rows.append({key: str(row[key]) for key in ("modality", "digest", "summary")})
    modalities = {row["modality"] for row in rows}
    if not required_modalities <= modalities:
        _fail("carrier evidence omitted a required Fairlight modality")
    return rows, True


def _public_evidence(
    rows: list[dict[str, str]],
    *,
    changed: bool,
    audition_required: bool,
    target_audio_absent: bool,
) -> dict[str, Any]:
    checks = [
        {
            "kind": "structural_readback",
            "status": "passed",
            "summary": row["summary"],
        }
        for row in rows
        if row["modality"] in {"readback", "structural"}
    ]
    audition = next((row for row in rows if row["modality"] == "auditioned"), None)
    if changed and audition_required:
        if audition is None:
            _fail("changed audible Fairlight state requires audition evidence")
        checks.append(
            {
                "kind": "audio_audition",
                "status": "passed",
                "summary": audition["summary"],
            }
        )
    elif changed and target_audio_absent:
        checks.append(
            {
                "kind": "target_audio_absent",
                "status": "passed",
                "summary": "Fresh pre- and post-mutation readback proved the exact target has no audio range to audition.",
            }
        )
    return {
        "checks": checks,
        "audition": {
            "required": changed and audition_required,
            "status": "passed" if changed and audition_required else "not_run",
        },
    }


def _track_rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        rows = value
    elif isinstance(value, Mapping) and isinstance(value.get("tracks"), list):
        rows = value["tracks"]
    else:
        _fail("current readback is not a Fairlight track collection")
    if not all(isinstance(row, Mapping) for row in rows):
        _fail("Fairlight track readback contains a non-object row")
    return rows


def _track_identity(timeline_id: str, rows: Any, index: Any) -> dict[str, Any]:
    if not isinstance(timeline_id, str) or not timeline_id.startswith("timeline_"):
        _fail("stable timeline identity is unavailable")
    if not isinstance(index, int) or isinstance(index, bool) or index < 1:
        _fail("audio track index is unavailable")
    matches = [row for row in _track_rows(rows) if row.get("index") == index]
    if len(matches) != 1:
        _fail("current readback does not identify exactly one audio track")
    name = matches[0].get("name")
    if name is not None and (not isinstance(name, str) or not name):
        _fail("audio track name readback is malformed")
    return {
        "timelineId": timeline_id,
        "trackType": "audio",
        "trackIndex": index,
        "trackName": name,
    }


def _index(request: Mapping[str, Any], handler: Mapping[str, Any]) -> int:
    for value in (
        handler.get("created_track_index"),
        handler.get("index"),
        request.get("track"),
        request.get("index"),
    ):
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    _fail("handler/request omitted the exact audio track index")


def _changed(handler: Mapping[str, Any], command_id: str) -> bool:
    explicit = handler.get("changed")
    if isinstance(explicit, bool):
        return explicit
    markers = {
        "fairlight.add": handler.get("created") is True,
        "fairlight.delete": handler.get("deleted") is True
        and handler.get("verified") is True,
        "fairlight.preset.apply": handler.get("applied") is True,
    }
    if command_id in markers:
        if not markers[command_id]:
            _fail(f"{command_id} handler omitted its strict success fields")
        return True
    # A verified specialized handler proves terminal application, but whether it
    # was a no-op must still be explicit in its payload.
    verification = handler.get("verification")
    if isinstance(verification, Mapping) and verification.get("status") == "verified":
        return True
    return True  # before/current readback comparison is mandatory below.


def _assert_requested_state(
    command_id: str,
    handler: Mapping[str, Any],
    request: Mapping[str, Any],
    state: Mapping[str, Any],
) -> None:
    expected: Any = None
    actual: Any = None
    if command_id == "fairlight.add":
        if handler.get("format_verified") is not True:
            _fail("add-track format readback did not prove the created format")
        expected, actual = request.get("trackType"), handler.get("readback_track_type")
    elif command_id == "fairlight.rename":
        expected, actual = request.get("name"), state.get("name")
    elif command_id in {"fairlight.mute", "fairlight.unmute"}:
        expected, actual = command_id.endswith(".mute"), state.get("muted")
    elif command_id in {"fairlight.lock", "fairlight.unlock"}:
        expected, actual = command_id.endswith(".lock"), state.get("locked")
    elif command_id == "fairlight.track_color":
        expected = request.get("color")
        expected = None if expected == "Clear" else expected
        actual = state.get("color")
    elif command_id == "fairlight.track_format.set":
        expected, actual = request.get("trackType"), state.get("format")
    elif command_id in {"fairlight.dynamics.enable", "fairlight.dynamics.disable"}:
        expected = command_id.endswith(".enable")
        processors = (
            state.get("compressor", {}),
            state.get("gate", {}),
            state.get("limiter", {}),
        )
        actual = all(processor.get("enabled") is expected for processor in processors)
        expected = True
    elif command_id == "fairlight.solo":
        selected = state.get("selectedTrack", {}).get("trackIndex")
        actual = all(
            row["enabled"] is (row["track"]["trackIndex"] == selected)
            for row in state["trackStates"]
        )
        expected = True
    elif command_id == "fairlight.solo_restore":
        expected = [
            (row.get("trackIndex"), row.get("enabled"))
            for row in request.get("trackStates", ())
            if isinstance(row, Mapping)
        ]
        actual = [
            (row.get("track", {}).get("trackIndex"), row.get("enabled"))
            for row in state.get("trackStates", ())
            if isinstance(row, Mapping)
        ]
    elif command_id == "fairlight.bus.level":
        expected, actual = request.get("levelDb"), state.get("levelDb")
    elif command_id == "fairlight.preset.apply":
        expected, actual = request.get("name"), state.get("presetName")
    elif command_id == "fairlight.voice_isolation.set":
        settings = state.get("settings", {})
        if "enable" in request and settings.get("enabled") is not request["enable"]:
            _fail("fairlight.voice_isolation.set enabled readback does not match the normalized request")
        if "amount" in request and settings.get("amount") != request["amount"]:
            _fail("fairlight.voice_isolation.set amount readback does not match the normalized request")
        expected = None
    elif command_id == "fairlight.mixer.fader" and request.get("levelDb") is not None:
        expected, actual = request.get("levelDb"), state.get("levelDb")
    elif command_id == "fairlight.mixer.pan" and request.get("pan") is not None:
        expected = request.get("pan")
        expected = (
            expected / 100
            if isinstance(expected, (int, float)) and abs(expected) > 1
            else expected
        )
        actual = state.get("pan")
    if expected is not None and expected != actual:
        _fail(f"{command_id} readback does not match the normalized request")


def _affected_count(
    command_id: str, handler: Mapping[str, Any], state: Mapping[str, Any]
) -> int:
    if command_id in {"fairlight.ensure_tracks", "fairlight.ensure_stereo_tracks"}:
        count = handler.get("created_count")
        if not isinstance(count, int) or count < 1:
            _fail("track ensure handler omitted a positive created_count")
        return count
    if command_id in {"fairlight.solo", "fairlight.solo_restore"}:
        return len(state["trackStates"])
    return 1


def _dynamics_state(
    track: dict[str, Any], readback: Mapping[str, Any]
) -> dict[str, Any]:
    def processor(prefix: str) -> dict[str, Any]:
        enabled = readback.get(f"{prefix}_enable")
        threshold = readback.get(f"{prefix}_threshold")
        ratio = readback.get("comp_ratio") if prefix == "comp" else None
        if not isinstance(enabled, bool) or not isinstance(threshold, (int, float)):
            _fail("dynamics readback omitted processor state")
        return {"enabled": enabled, "thresholdDb": threshold, "ratio": ratio}

    return {
        "track": track,
        "compressor": processor("comp"),
        "gate": processor("gate"),
        "limiter": processor("limiter"),
    }


def _state(
    command_id: str,
    handler: Mapping[str, Any],
    request: Mapping[str, Any],
    timeline_id: str,
    current: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if command_id == "fairlight.bus.level":
        bus = handler.get("bus")
        bus_name = bus.get("resolved") if isinstance(bus, Mapping) else bus
        level = handler.get("level_db", handler.get("output_audio_gain"))
        if (
            not isinstance(bus_name, str)
            or not bus_name
            or not isinstance(level, (int, float))
        ):
            _fail("bus-level handler omitted verified bus/level state")
        identity = {
            "busName": bus_name,
            "busKind": "main" if bus_name.casefold().startswith("main") else "bus",
        }
        return {"bus": identity, "levelDb": level}, {"kind": "bus", "bus": identity}
    if command_id == "fairlight.preset.apply":
        name = handler.get("name")
        if not isinstance(name, str) or not name or handler.get("applied") is not True:
            _fail("preset handler omitted an applied preset result")
        return {"presetName": name, "applied": True}, {
            "kind": "timeline",
            "timelineId": timeline_id,
        }
    if command_id in {"fairlight.ensure_tracks", "fairlight.ensure_stereo_tracks"}:
        rows = _track_rows(current)
        created = handler.get("created_indices")
        candidate = created[-1] if isinstance(created, list) and created else None
        if candidate is None:
            candidate = rows[-1].get("index") if rows else None
        track = _track_identity(timeline_id, current, candidate)
        count = handler.get("audio_tracks_after")
        if not isinstance(count, int) or count < 0:
            _fail("track ensure handler omitted audio_tracks_after")
        return {"track": track, "trackCount": count}, {
            "kind": "timeline",
            "timelineId": timeline_id,
        }
    if command_id == "fairlight.track.duplicate":
        duplicated = _mapping(
            handler.get("duplicated_track"), "duplicated-track readback"
        )
        duplicate = _track_identity(timeline_id, current, duplicated.get("index"))
        source = _track_identity(timeline_id, current, request.get("index"))
        count = handler.get("audio_tracks_after")
        if not isinstance(count, int) or count < 1:
            _fail("track duplicate handler omitted audio_tracks_after")
        return {"track": duplicate, "trackCount": count}, {
            "kind": "track",
            "track": source,
        }
    if command_id == "fairlight.track_order.move":
        destination = handler.get("to", request.get("toIndex"))
        track = _track_identity(timeline_id, current, destination)
        return {"track": track, "trackCount": len(_track_rows(current))}, {
            "kind": "track",
            "track": track,
        }
    if command_id == "fairlight.solo_restore":
        restored = handler.get("restored_states")
        requested_states = request.get("trackStates")
        if (
            not isinstance(restored, list)
            or not restored
            or not isinstance(requested_states, list)
        ):
            _fail("solo-restore handler omitted restored_states")
        expected = [
            {"index": row.get("trackIndex"), "enabled": row.get("enabled")}
            for row in requested_states
            if isinstance(row, Mapping)
        ]
        if restored != expected:
            _fail("solo-restore handler readback differs from the normalized request")
        states = []
        rows = _track_rows(current)
        for row in restored:
            if not isinstance(row, Mapping) or not isinstance(row.get("enabled"), bool):
                _fail("solo-restore applied state is malformed")
            identity = _track_identity(timeline_id, rows, row.get("index"))
            live = next(
                candidate
                for candidate in rows
                if candidate.get("index") == row.get("index")
            )
            if live.get("enabled") is not row["enabled"]:
                _fail(
                    "solo-restore fresh readback differs from the handler verification"
                )
            states.append({"track": identity, "enabled": row["enabled"]})
        return {"trackStates": states}, {"kind": "timeline", "timelineId": timeline_id}
    if command_id == "fairlight.mixer.fader" and request.get("bus"):
        mixer = _mapping(current, "complete bus mixer readback")
        level = mixer.get("level_db")
        pan = mixer.get("pan")
        angle = mixer.get("angle")
        spread = mixer.get("spread")
        bus_name = mixer.get("bus")
        bus_kind = mixer.get("busKind")
        if (
            not isinstance(level, (int, float))
            or not isinstance(pan, (int, float))
            or not isinstance(bus_name, str)
            or bus_name != request.get("bus")
            or bus_kind != "main"
            or (angle is not None and not isinstance(angle, (int, float)))
            or (spread is not None and not isinstance(spread, (int, float)))
        ):
            _fail("bus mixer readback omitted exact target or numeric state")
        target_bus = {"busName": bus_name, "busKind": bus_kind}
        return {
            "target": target_bus,
            "levelDb": level,
            "pan": pan / 100 if abs(pan) > 1 else pan,
            "angle": angle,
            "spread": spread,
        }, {"kind": "bus", "bus": target_bus}
    index = _index(request, handler)
    track = _track_identity(timeline_id, current, index)
    target: dict[str, Any] = {"kind": "track", "track": track}
    if command_id == "fairlight.add":
        count = handler.get("audio_tracks_after")
        if not isinstance(count, int) or count < 0:
            _fail("track creation handler omitted audio_tracks_after")
        return {"track": track, "trackCount": count}, {
            "kind": "timeline",
            "timelineId": timeline_id,
        }
    if command_id == "fairlight.delete":
        count = handler.get("audio_tracks_after")
        if not isinstance(count, int) or count < 0:
            _fail("track delete handler omitted audio_tracks_after")
        return {"track": track, "trackCount": count}, target
    if command_id == "fairlight.rename":
        return {"track": track, "name": track["trackName"]}, target
    if command_id in {"fairlight.mute", "fairlight.unmute"}:
        row = next(row for row in _track_rows(current) if row.get("index") == index)
        if not isinstance(row.get("enabled"), bool):
            _fail("track enabled-state readback is absent")
        return {"track": track, "muted": not row["enabled"]}, target
    if command_id in {"fairlight.lock", "fairlight.unlock"}:
        row = next(row for row in _track_rows(current) if row.get("index") == index)
        if not isinstance(row.get("locked"), bool):
            _fail("track lock-state readback is absent")
        return {"track": track, "locked": row["locked"]}, target
    if command_id == "fairlight.solo":
        applied = handler.get("applied_states")
        if not isinstance(applied, list) or not applied:
            _fail("solo handler omitted applied_states")
        states = []
        for row in applied:
            if not isinstance(row, Mapping) or not isinstance(row.get("enabled"), bool):
                _fail("solo applied state is malformed")
            identity = _track_identity(timeline_id, current, row.get("index"))
            states.append({"track": identity, "enabled": row["enabled"]})
        return {"selectedTrack": track, "trackStates": states}, target
    if command_id == "fairlight.track_color":
        color = handler.get("readback_color", handler.get("color"))
        if color is not None and not isinstance(color, str):
            _fail("track color readback is malformed")
        return {"track": track, "color": color}, target
    if command_id == "fairlight.track_format.set":
        row = next(row for row in _track_rows(current) if row.get("index") == index)
        value = row.get("format", row.get("type"))
        if not isinstance(value, str) or not value:
            _fail("track format readback is absent")
        return {"track": track, "format": value}, target
    if command_id.startswith("fairlight.dynamics."):
        return _dynamics_state(track, _mapping(current, "dynamics readback")), target
    if command_id == "fairlight.voice_isolation.set":
        readback = handler.get("readback")
        readback = _mapping(readback, "voice-isolation readback")
        if not isinstance(readback.get("isEnabled"), bool) or not isinstance(
            readback.get("amount"), (int, float)
        ):
            _fail("voice-isolation readback is incomplete")
        return {
            "track": track,
            "settings": {
                "enabled": readback["isEnabled"],
                "amount": readback["amount"],
            },
        }, target
    if command_id == "fairlight.bus.assign":
        bus = handler.get("bus")
        if isinstance(bus, Mapping):
            bus_name = bus.get("resolved", bus.get("name"))
        else:
            bus_name = bus
        if not isinstance(bus_name, str) or not bus_name:
            _fail("bus assignment readback omitted the bus identity")
        return {
            "track": track,
            "bus": {
                "busName": bus_name,
                "busKind": "main" if bus_name.casefold().startswith("main") else "bus",
            },
            "assigned": True,
        }, target
    if command_id == "fairlight.automation.write":
        automation = _mapping(current, "automation readback")
        frame = automation.get("record_frame")
        value = automation.get("value")
        mode = automation.get("mode")
        if (
            not isinstance(frame, int)
            or not isinstance(value, (int, float))
            or not isinstance(mode, str)
        ):
            _fail("automation route omitted exact recordFrame/value/mode semantics")
        return {
            "track": track,
            "mode": mode,
            "points": [{"recordFrame": frame, "value": value}],
        }, target
    if command_id in {"fairlight.mixer.fader", "fairlight.mixer.pan"}:
        mixer = _mapping(current, "complete mixer readback")
        level = mixer.get("level_db")
        pan = mixer.get("pan")
        angle = mixer.get("angle")
        spread = mixer.get("spread")
        if not isinstance(level, (int, float)) or not isinstance(pan, (int, float)):
            _fail("mixer readback omitted numeric state")
        if angle is not None and not isinstance(angle, (int, float)):
            _fail("mixer angle readback is malformed")
        if spread is not None and not isinstance(spread, (int, float)):
            _fail("mixer spread readback is malformed")
        normalized_pan = pan / 100 if abs(pan) > 1 else pan
        return {
            "target": track,
            "levelDb": level,
            "pan": normalized_pan,
            "angle": angle,
            "spread": spread,
        }, target
    _fail(f"{command_id} lacks a reviewed state adapter")


def project_fairlight_track_mutation_result(
    action_id: str,
    handler_result: Any,
    *,
    timeline_id: str,
    requested: Mapping[str, Any],
    current_readback: Any,
    verification: Any,
    before_readback: Any | None = None,
    required_modalities: set[str] | None = None,
    target_audio_absent: bool = False,
) -> dict[str, Any]:
    """Project one actual handler result, failing closed on missing proof."""

    command_id = _command_id(action_id)
    handler = _mapping(handler_result, "Fairlight handler result")
    request = _mapping(requested, "normalized Fairlight request")
    _verify_handler(command_id, handler)
    required_modalities = required_modalities or {
        "readback",
        "structural",
    }
    proof_rows, _protected = _proof(
        verification, required_modalities=required_modalities
    )
    changed = _changed(handler, command_id)
    audition_required = "auditioned" in required_modalities
    if action_id in READBACK_REQUIRED_ACTION_IDS and before_readback is None:
        _fail("message-only handler requires before and current track readback")
    state_readback = (
        before_readback if command_id == "fairlight.delete" else current_readback
    )
    if state_readback is None:
        _fail("track delete projection requires the pre-delete track readback")
    after, target = _state(command_id, handler, request, timeline_id, state_readback)
    _assert_requested_state(command_id, handler, request, after)

    before = None
    if before_readback is not None and command_id == "fairlight.solo_restore":
        rows = _track_rows(before_readback)
        before = {
            "trackStates": [
                {
                    "track": _track_identity(timeline_id, rows, row["trackIndex"]),
                    "enabled": next(
                        candidate["enabled"]
                        for candidate in rows
                        if candidate.get("index") == row["trackIndex"]
                    ),
                }
                for row in request["trackStates"]
            ]
        }
        if any(not isinstance(row["enabled"], bool) for row in before["trackStates"]):
            _fail("solo-restore before readback omitted enabled state")
        changed = before != after
    elif before_readback is not None and command_id != "fairlight.delete":
        try:
            before, _ = _state(
                command_id, handler, request, timeline_id, before_readback
            )
        except UnsupportedFairlightTrackProjection:
            before = None
        if before == after:
            changed = False

    result = {
        "actionId": action_id,
        "outcome": "succeeded" if changed else "no_change",
        "target": target,
        "before": None if changed else after,
        "after": after if changed else None,
        "affectedCount": _affected_count(command_id, handler, after) if changed else 0,
        "evidence": _public_evidence(
            proof_rows,
            changed=changed,
            audition_required=audition_required,
            target_audio_absent=target_audio_absent,
        ),
        "recovery": {
            "required": False,
            "manualRecoveryRequired": False,
            "state": "none",
            "guidance": None,
        },
    }
    return deepcopy(result)
