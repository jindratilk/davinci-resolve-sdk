"""Production owners for exact ordinary Timeline prepared actions.

This module is private runtime code.  Public inputs remain stable SDK identities;
native object selection, checkpoint custody, execution and verification stay here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import RLock
from types import MappingProxyType
from typing import Any, Callable, Mapping

from ..connection import get_connection
from ..core import fairlight_ops, timeline_ops, version_ops
from ..core.sdk_live_inspection import documented_unique_id
from ..utils.timecode import frames_to_timecode
from .timeline_contracts import timeline_action_input_schema
from .timeline_read_prepared_action import _digest, _matches_schema, _record, _range, _setting_value
from .timeline_version import TIMELINE_VERSION_MUTATION_DESCRIPTORS
from .timeline_version_prepared_action import (
    TimelineVersionPreparedActionDescriptor,
    _unsupported_production_execute,
)


TIMELINE_ORDINARY_ACTION_IDS = (
    "cutagent.action.timeline.clip_color.batch",
    "cutagent.action.timeline.create",
    "cutagent.action.timeline.delete",
    "cutagent.action.timeline.duplicate",
    "cutagent.action.timeline.fairlight_preset.apply",
    "cutagent.action.timeline.import",
    "cutagent.action.timeline.mark.clear",
    "cutagent.action.timeline.mark.set",
    "cutagent.action.timeline.playhead.set",
    "cutagent.action.timeline.rename",
    "cutagent.action.timeline.set_start_tc",
    "cutagent.action.timeline.settings_set",
    "cutagent.action.timeline.output_blanking.set",
    "cutagent.action.timeline.start_tc",
    "cutagent.action.timeline.switch",
)
TIMELINE_ANALYSIS_ACTION_IDS = ("cutagent.action.timeline.dolby.analyze",)
TIMELINE_ORDINARY_PRODUCTION_ACTION_IDS = (*TIMELINE_ORDINARY_ACTION_IDS, *TIMELINE_ANALYSIS_ACTION_IDS)

_PROJECT_ACTIONS = frozenset({
    "cutagent.action.timeline.create", "cutagent.action.timeline.delete",
    "cutagent.action.timeline.duplicate", "cutagent.action.timeline.import",
    "cutagent.action.timeline.rename", "cutagent.action.timeline.switch",
})
_CHECKPOINTS: dict[str, Mapping[str, Any]] = {}
_CHECKPOINT_LOCK = RLock()


def _execution_phase(phase: str, operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except Exception as failure:
        try:
            failure.prepared_action_substage = phase
        except Exception:
            pass
        raise


def _pre_mutation_phase(phase: str, operation: Callable[[], Any]) -> Any:
    try:
        return _execution_phase(phase, operation)
    except Exception as failure:
        try:
            failure.possible_mutation = "none"
        except Exception:
            pass
        raise


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("Timeline state contains a non-finite number.")
        return value
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return str(value)


def _sha256(value: Any) -> str:
    raw = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _timeline_rows(conn: Any, project_id: str) -> list[dict[str, Any]]:
    rows = []
    inventory = timeline_ops.list_timelines(conn, authoritative_ids=True)
    for source in inventory:
        index = int(source["index"])
        timeline = conn.project.GetTimelineByIndex(index)
        native_id = documented_unique_id(timeline) if timeline else None
        name = source.get("name")
        if not native_id or not isinstance(name, str) or not name:
            raise ValueError("Timeline inventory lacks an authoritative native identity.")
        if source.get("timeline_id") != native_id:
            raise ValueError("Timeline inventory identity changed during capture.")
        public_id = _digest("timeline_", {"projectId": project_id, "nativeId": native_id})
        rows.append({
            "timeline": timeline, "nativeId": native_id, "timelineId": public_id,
            "name": name, "index": index,
            "revision": _digest("revision_", source),
        })
    return rows


def _row_by_id(rows: list[dict[str, Any]], timeline_id: str) -> dict[str, Any]:
    matches = [row for row in rows if row["timelineId"] == timeline_id]
    if len(matches) != 1:
        raise ValueError("Timeline target is missing or ambiguous.")
    return matches[0]


def _unique_name_target(rows: list[dict[str, Any]], timeline_id: str) -> dict[str, Any]:
    row = _row_by_id(rows, timeline_id)
    if sum(candidate["name"] == row["name"] for candidate in rows) != 1:
        raise ValueError("Native Timeline selection by name would be ambiguous.")
    return row


def _item_rows_for_timeline(timeline: Any, timeline_id: str) -> list[dict[str, Any]]:
    rows = []
    for track_type in ("video", "audio", "subtitle"):
        for index in range(1, int(timeline.GetTrackCount(track_type) or 0) + 1):
            for item in timeline.GetItemListInTrack(track_type, index) or []:
                native_id = documented_unique_id(item)
                if not native_id:
                    raise ValueError("Timeline item lacks an authoritative native identity.")
                rows.append({
                    "item": item,
                    "timelineItemId": _digest("timeline_item_", {"timelineId": timeline_id, "nativeId": native_id}),
                    "nativeId": native_id, "trackType": track_type, "trackIndex": index,
                    "name": str(item.GetName() or ""),
                    "start": int(item.GetStart()), "end": int(item.GetEnd()),
                    "clipColor": str(item.GetClipColor() or "") if callable(getattr(item, "GetClipColor", None)) else None,
                })
    native_ids = [row["nativeId"] for row in rows]
    if len(set(native_ids)) != len(native_ids):
        raise ValueError("Timeline item inventory has duplicate native identities.")
    readable_native_ids = set(native_ids)
    for row in rows:
        getter = getattr(row["item"], "GetLinkedItems", None)
        if not callable(getter):
            raise ValueError("Timeline item linkage readback is unavailable.")
        try:
            linked_items = getter()
        except Exception as exc:
            raise ValueError("Timeline item linkage readback failed.") from exc
        if not isinstance(linked_items, (list, tuple)):
            raise ValueError("Timeline item linkage readback is incomplete.")
        linked_native_ids = []
        for linked in linked_items:
            linked_native_id = documented_unique_id(linked)
            if (
                not linked_native_id
                or linked_native_id == row["nativeId"]
                or linked_native_id not in readable_native_ids
            ):
                raise ValueError("Timeline item linkage escaped the readable snapshot.")
            linked_native_ids.append(linked_native_id)
        if len(set(linked_native_ids)) != len(linked_native_ids):
            raise ValueError("Timeline item linkage contains duplicate identities.")
        row["linkedNativeIds"] = sorted(linked_native_ids)
    links_by_id = {
        row["nativeId"]: set(row["linkedNativeIds"])
        for row in rows
    }
    if any(
        native_id not in links_by_id.get(linked_native_id, set())
        for native_id, linked_native_ids in links_by_id.items()
        for linked_native_id in linked_native_ids
    ):
        raise ValueError("Timeline item linkage is not reciprocal.")
    return rows


def _item_rows(conn: Any, timeline_id: str) -> list[dict[str, Any]]:
    return _item_rows_for_timeline(conn.timeline, timeline_id)


def _timeline_structure(timeline: Any, timeline_id: str) -> dict[str, Any]:
    items = [
        {
            key: row[key]
            for key in (
                "timelineItemId", "nativeId", "trackType", "trackIndex",
                "start", "end", "linkedNativeIds",
            )
        }
        for row in _item_rows_for_timeline(timeline, timeline_id)
    ]
    tracks = []
    for track_type in ("video", "audio", "subtitle"):
        for index in range(1, int(timeline.GetTrackCount(track_type) or 0) + 1):
            row = {
                "trackType": track_type,
                "trackIndex": index,
                "name": str(timeline.GetTrackName(track_type, index) or ""),
            }
            for field, method_name in (
                ("enabled", "GetIsTrackEnabled"),
                ("locked", "GetIsTrackLocked"),
                ("subtype", "GetTrackSubType"),
            ):
                getter = getattr(timeline, method_name, None)
                if callable(getter):
                    row[field] = _canonical(getter(track_type, index))
            tracks.append(row)
    return {"items": items, "tracks": tracks}


def _active_state(conn: Any, project_id: str) -> dict[str, Any]:
    timeline = conn.project.GetCurrentTimeline()
    if not timeline:
        return {"timelineId": None, "name": None, "structure": None}
    native_id = documented_unique_id(timeline)
    if not native_id:
        raise ValueError("Current Timeline lacks an authoritative native identity.")
    timeline_id = _digest("timeline_", {"projectId": project_id, "nativeId": native_id})
    marks = timeline_ops.get_mark_in_out(conn).get("marks")
    settings = timeline_ops.get_timeline_settings(conn)
    playhead = timeline_ops.get_playhead(conn)
    structure = _timeline_structure(timeline, timeline_id)
    return {
        "timelineId": timeline_id, "name": str(timeline.GetName() or "Unnamed"),
        "nativeId": native_id, "marks": _canonical(marks),
        "settings": _canonical(settings), "playhead": _canonical(playhead),
        "startFrame": int(timeline.GetStartFrame()),
        "endFrame": int(timeline.GetEndFrame()),
        "startTimecode": timeline.GetStartTimecode() if hasattr(timeline, "GetStartTimecode") else None,
        **structure,
    }


def _state(conn: Any, project_id: str, blanking_value=None) -> dict[str, Any]:
    native_project_id = documented_unique_id(conn.project)
    if not native_project_id:
        raise ValueError("Active project lacks an authoritative native identity.")
    timelines = _timeline_rows(conn, project_id)
    active = _active_state(conn, project_id)
    if blanking_value is not None:
        from . import output_blanking
        active["outputBlanking"] = output_blanking.read(conn, blanking_value)
        active["outputBlankingAll"] = output_blanking.output_blanking.snapshot(conn)
    public = {
        "projectNativeId": native_project_id,
        "timelines": [{key: row[key] for key in ("timelineId", "nativeId", "name", "index", "revision")} for row in timelines],
        "timelineStructures": {
            row["timelineId"]: _timeline_structure(row["timeline"], row["timelineId"])
            for row in timelines
        },
        "active": active,
    }
    return {**public, "revision": _digest("revision_", public)}


def _validate_input(action_id: str, value: Any) -> Mapping[str, Any]:
    command_id = action_id.removeprefix("cutagent.action.")
    schema = timeline_action_input_schema(command_id)
    if not isinstance(value, Mapping) or not _matches_schema(schema, value):
        raise ValueError("Timeline mutation input does not match its exact public schema.")
    if action_id == "cutagent.action.timeline.output_blanking.set":
        if value["operation"]["kind"] == "inheritance" and "timelineItemId" not in value:
            raise ValueError("Specify four blanking edges or exact clip inheritance.")
    if action_id == "cutagent.action.timeline.dolby.analyze" and value.get("enableProjectControls") is not False:
        raise ValueError("SDK Dolby analysis requires project controls to remain disabled.")
    return _canonical(value)


def _assert_carrier(context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]) -> None:
    request = context.get("exactRequestBinding")
    mutation_base = context.get("mutationBase")
    if not isinstance(request, Mapping) or not isinstance(mutation_base, Mapping):
        raise ValueError("Timeline action lacks its exact signed request binding.")
    identities = request.get("identities")
    revisions = request.get("revisions")
    target_ids = identities.get("targetIds") if isinstance(identities, Mapping) else None
    target_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
    if (
        not isinstance(identities, Mapping)
        or not isinstance(revisions, Mapping)
        or identities.get("projectId") != value.get("projectId")
        or not isinstance(target_ids, (list, tuple))
        or not target_ids
        or len(set(target_ids)) != len(target_ids)
        or not isinstance(target_revisions, Mapping)
        or set(target_revisions) != set(target_ids)
    ):
        raise ValueError("Timeline action exact target binding is incomplete.")
    project_bound = action_id in _PROJECT_ACTIONS
    expected_level = "project" if project_bound else "project+timeline"
    if mutation_base.get("carrier") != "sdk" or mutation_base.get("minimumBinding") != expected_level:
        raise ValueError("Timeline action carrier binding level is invalid.")
    if project_bound:
        if revisions.get("project") != value.get("revision"):
            raise ValueError("Timeline action project revision is stale.")
    else:
        requested_revision = value.get("revision", value.get("operation", {}).get("revision"))
        if (
            identities.get("timelineId") != value.get("timelineId")
            or not isinstance(revisions.get("timeline"), str)
            or (requested_revision is not None and revisions.get("timeline") != requested_revision)
        ):
            raise ValueError("Timeline action Timeline revision is stale.")
    if mutation_base.get("operationId") != context.get("operationId"):
        raise ValueError("Timeline action operation custody changed.")
    if action_id == "cutagent.action.timeline.import":
        private = context.get("privateBindings")
        topology = private.get("timelineTopology") if isinstance(private, Mapping) else None
        input_file = topology.get("inputFile") if isinstance(topology, Mapping) else None
        digest = input_file.get("sha256") if isinstance(input_file, Mapping) else None
        referenced_payload_digests = mutation_base.get("referencedPayloadDigests")
        if (
            not isinstance(digest, str)
            or not isinstance(referenced_payload_digests, (list, tuple))
            or tuple(referenced_payload_digests) != (digest,)
        ):
            raise ValueError("Timeline import lacks a signed frozen payload digest.")


def _captured_import_path(context: Mapping[str, Any]) -> str:
    private = context.get("privateBindings")
    topology = private.get("timelineTopology") if isinstance(private, Mapping) else None
    record = topology.get("inputFile") if isinstance(topology, Mapping) else None
    path = Path(record.get("absolutePath", "")) if isinstance(record, Mapping) else None
    try:
        stat = path.lstat() if path is not None else None
    except OSError as exc:
        raise ValueError("Timeline import frozen payload is unavailable.") from exc
    identity = tuple(map(str, (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns))) if stat else ()
    expected = tuple(record.get(key) for key in ("device", "inode", "size", "mtimeNs")) if isinstance(record, Mapping) else ()
    if (
        path is None
        or stat is None
        or not path.is_file()
        or path.is_symlink()
        or identity != expected
        or "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != record.get("sha256")
    ):
        raise ValueError("Timeline import frozen payload changed after authorization.")
    return str(path)


def _checkpoint(context: Mapping[str, Any], action_id: str, conn: Any) -> Mapping[str, Any]:
    operation_id = str(context.get("operationId") or "")
    if not operation_id:
        raise ValueError("Timeline action lacks a durable operation identity.")
    checkpoint_id = "chk_sdk_" + hashlib.sha256(
        f"{operation_id}:{action_id}".encode()
    ).hexdigest()[:32]
    with _CHECKPOINT_LOCK:
        existing = _CHECKPOINTS.get(operation_id)
        if existing is not None:
            return existing
        _CHECKPOINTS[operation_id] = MappingProxyType({"id": checkpoint_id})
        return _CHECKPOINTS[operation_id]


def _ensure_checkpoint(
    context: Mapping[str, Any], action_id: str, prepared: Mapping[str, Any], conn: Any,
) -> None:
    checkpoint_id = str(prepared["domain"]["checkpointId"])
    session = context.get("session")
    session_id = session.get("sessionId") if isinstance(session, Mapping) else None
    existing = version_ops.get_checkpoint(checkpoint_id)
    if existing is not None:
        if existing.get("session_id") != session_id:
            raise ValueError("Timeline checkpoint identity collided with unrelated state.")
        return
    created = version_ops.create_checkpoint(
        conn, label=f"SDK pre-mutation checkpoint: {action_id}",
        kind="manual_commit", session_id=session_id,
        exact_checkpoint_id=checkpoint_id,
    )
    if created.get("id") != checkpoint_id:
        raise ValueError("Timeline checkpoint lost its exact operation identity.")


def _authority(context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]) -> Mapping[str, Any]:
    _assert_carrier(context, action_id, value)
    project = context.get("project")
    timeline_context = context.get("timeline")
    if not isinstance(project, Mapping) or value.get("projectId") != project.get("projectId"):
        raise ValueError("Timeline action project identity is stale.")
    conn = get_connection(
        require_project=True,
        require_timeline=action_id not in _PROJECT_ACTIONS,
    )
    project_id = str(project["projectId"])
    before = (_state(conn, project_id, value) if action_id == "cutagent.action.timeline.output_blanking.set" else _state(conn, project_id))
    private = context.get("privateBindings")
    if isinstance(private, Mapping):
        expected = private.get("nativeProjectId")
        if expected is not None and expected != before["projectNativeId"]:
            raise ValueError("Native project identity changed after carrier capture.")
    descriptor = TIMELINE_VERSION_MUTATION_DESCRIPTORS[action_id]
    timeline = None
    if descriptor.binding_level == "project+timeline":
        if not isinstance(timeline_context, Mapping) or value.get("timelineId") != timeline_context.get("timelineId"):
            raise ValueError("Timeline action Timeline identity is stale.")
        timeline = {"id": str(timeline_context["timelineId"]), "revision": str(timeline_context["timelineRevision"])}
        if before["active"]["timelineId"] != timeline["id"]:
            raise ValueError("Timeline action is not bound to the exact active Timeline.")
    rows = _timeline_rows(conn, project_id)
    resolved: list[dict[str, Any]]
    if action_id in {"cutagent.action.timeline.create", "cutagent.action.timeline.import"}:
        resolved = [{"kind": "project", "stableId": project_id, "revision": str(project["projectRevision"])}]
    elif action_id in {"cutagent.action.timeline.clip_color.batch", "cutagent.action.timeline.dolby.analyze"}:
        items = _item_rows(conn, str(timeline["id"]))
        requested = (
            [row["timelineItemId"] for row in value["updates"]]
            if action_id == "cutagent.action.timeline.clip_color.batch"
            else list(value.get("timelineItemIds") or [])
        )
        by_public_id = {row["timelineItemId"]: row for row in items}
        if len(by_public_id) != len(items) or any(item_id not in by_public_id for item_id in requested):
            raise ValueError("Timeline item target set is missing or ambiguous.")
        selected = [by_public_id[item_id] for item_id in requested]
        if action_id == "cutagent.action.timeline.clip_color.batch":
            for update, row in zip(value["updates"], selected):
                if (
                    update["trackType"] != row["trackType"]
                    or update["trackIndex"] != row["trackIndex"]
                    or update["recordStartFrame"] != row["start"]
                    or update["recordEndFrame"] != row["end"]
                    or update["name"] != row["name"]
                ):
                    raise ValueError("Timeline clip-color target changed after snapshot capture.")
        resolved = [{
            "kind": "clip", "stableId": row["timelineItemId"], "publicId": row["timelineItemId"],
            "nativeId": row["nativeId"],
            "revision": str(timeline["revision"]),
            "trackType": row["trackType"], "trackIndex": row["trackIndex"],
            "name": row["name"], "start": row["start"], "end": row["end"],
        } for row in selected]
    elif descriptor.binding_level == "project":
        field = "sourceTimelineId" if action_id.endswith(".duplicate") else "timelineId"
        row = _row_by_id(rows, str(value[field]))
        resolved = [{"kind": "timeline", "stableId": row["timelineId"], "publicId": row["timelineId"], "nativeId": row["nativeId"], "revision": str(project["projectRevision"])}]
    else:
        row = _row_by_id(rows, str(timeline["id"]))
        resolved = [{"kind": "timeline", "stableId": row["timelineId"], "publicId": row["timelineId"], "nativeId": row["nativeId"], "revision": str(timeline["revision"])}]
    checkpoint = _checkpoint(context, action_id, conn)
    checkpoint_id = str(checkpoint["id"])
    return {
        "stale": False, "ambiguous": False, "complete": True, "broad": False,
        "project": {"id": project_id, "revision": str(project["projectRevision"])},
        **({"timeline": timeline} if timeline else {}),
        "resolvedTargets": resolved,
        "closedComposition": descriptor.closed_composition,
        "linkedTopologyComplete": True,
        "privatePreState": {
            "targetStableIds": sorted(row["stableId"] for row in resolved),
            "protectedStateDigest": _sha256(before),
            "nativeProjectId": before["projectNativeId"],
            "activeContext": {"projectId": project_id, **({"timelineId": timeline["id"]} if timeline else {})},
        },
        "checkpointId": checkpoint_id, "checkpointProjectId": project_id,
        **({"checkpointTimelineId": timeline["id"]} if timeline else {}),
    }


def _impact(context: Mapping[str, Any], _action_id: str, effect: Mapping[str, Any]) -> Mapping[str, Any]:
    base = context.get("mutationBase")
    if not isinstance(base, Mapping):
        raise ValueError("Timeline mutation lacks its carrier mutation base.")
    return {
        **_canonical(base), "status": "mutation", "complete": True,
        "closedComposition": True, "ambiguous": False, "broad": False,
        "executableStableTargetPrecondition": True, "effects": [_canonical(effect)],
        "verificationPolicy": {
            "minimumEvidence": ["readback"],
            "requireProtectedStatePreserved": True,
            "protectedTargetEvidence": "every_declared_target",
        },
    }


def _position(conn: Any, value: Mapping[str, Any]) -> str:
    inner = value["value"]
    if inner["kind"] != "frames":
        return str(inner["value"])
    start_frame = int(conn.timeline.GetStartFrame())
    relative_frame = int(inner["value"]) - start_frame
    if relative_frame < 0:
        raise ValueError("Timeline-record frame precedes the Timeline start frame.")
    return f"{relative_frame}f"


def _fairlight_digest(conn: Any) -> str:
    track_count = int(conn.timeline.GetTrackCount("audio") or 0)
    snapshot = [fairlight_ops.get_audio_track_info(conn, index) for index in range(1, track_count + 1)]
    return _sha256(snapshot)


def _start_timecode(value: Mapping[str, Any], fps: float) -> str:
    inner = value["value"]
    if inner["kind"] == "timecode":
        return str(inner["value"])
    return frames_to_timecode(int(inner["value"]), fps)


def _native_timeline_setting_value(setting: Mapping[str, Any]) -> Any:
    kind = setting.get("kind")
    if kind == "boolean" and isinstance(setting.get("value"), bool):
        return "1" if setting["value"] else "0"
    if kind == "number" and isinstance(setting.get("value"), (int, float)) and not isinstance(setting.get("value"), bool):
        return setting["value"]
    if kind == "text" and isinstance(setting.get("value"), str):
        return setting["value"]
    raise ValueError("Timeline setting value has no supported native scalar lowering.")


def _execute(context: Mapping[str, Any], command_id: str, value: Mapping[str, Any], prepared: Mapping[str, Any]) -> Mapping[str, Any]:
    action_id = "cutagent.action." + command_id
    _pre_mutation_phase(
        "timeline.carrier_revalidation",
        lambda: _assert_carrier(context, action_id, value),
    )
    conn = _pre_mutation_phase(
        "timeline.connection",
        lambda: get_connection(
            require_project=True,
            require_timeline=action_id not in _PROJECT_ACTIONS,
        ),
    )
    expected_native_project_id = prepared.get("domain", {}).get(
        "privateCanonicalPreState", {}
    ).get("nativeProjectId")
    _pre_mutation_phase(
        "timeline.native_project_revalidation",
        lambda: _require(
            bool(expected_native_project_id)
            and documented_unique_id(conn.project) == expected_native_project_id,
            "Native project identity changed immediately before execution.",
        ),
    )
    project_id = str(value["projectId"])
    before = _pre_mutation_phase(
        "timeline.before_state", lambda: (_state(conn, project_id, value) if action_id == "cutagent.action.timeline.output_blanking.set" else _state(conn, project_id))
    )
    before_fairlight = (
        _pre_mutation_phase(
            "timeline.fairlight_before_state", lambda: _fairlight_digest(conn)
        )
        if command_id == "timeline.fairlight_preset.apply"
        else None
    )
    _pre_mutation_phase(
        "timeline.active_timeline_revalidation",
        lambda: _require(
            action_id in _PROJECT_ACTIONS
            or before["active"]["timelineId"] == value.get("timelineId"),
            "Active Timeline changed after prepared authorization.",
        ),
    )
    rows = _pre_mutation_phase(
        "timeline.target_revalidation", lambda: _timeline_rows(conn, project_id)
    )
    _pre_mutation_phase(
        "timeline.mutation_boundary_revalidation",
        lambda: _require(
            documented_unique_id(conn.project) == expected_native_project_id,
            "Native project identity changed at the mutation boundary.",
        ),
    )
    _execution_phase(
        "timeline.checkpoint",
        lambda: _ensure_checkpoint(context, action_id, prepared, conn),
    )
    raw: Any
    created = None
    if command_id == "timeline.create":
        created = timeline_ops.create_timeline(conn, value["name"], value.get("width"), value.get("height"), value.get("frameRate")); raw = {"created": True}
    elif command_id == "timeline.delete":
        row = _unique_name_target(rows, value["timelineId"])
        if before["active"]["timelineId"] == value["timelineId"] and value["force"] is not True:
            raise ValueError("Deleting the active Timeline requires force=true.")
        raw = timeline_ops.delete_timeline(conn, row["name"])
    elif command_id == "timeline.duplicate":
        row = _unique_name_target(rows, value["sourceTimelineId"]); raw = timeline_ops.duplicate_timeline(conn, value["newName"], row["name"])
    elif command_id == "timeline.import":
        created = timeline_ops.import_timeline(conn, _captured_import_path(context)); raw = {"imported": True}
    elif command_id == "timeline.rename":
        row = _unique_name_target(rows, value["timelineId"]); raw = timeline_ops.rename_timeline(conn, value["newName"], source_name=row["name"], return_details=True)
    elif command_id == "timeline.switch":
        row = _unique_name_target(rows, value["timelineId"]); raw = timeline_ops.switch_timeline(conn, name=row["name"], return_details=True)
    elif command_id == "timeline.fairlight_preset.apply":
        raw = fairlight_ops.apply_fairlight_preset(conn, value["presetName"])
    elif command_id == "timeline.mark.set":
        marked = value["range"]; raw = timeline_ops.set_mark_in_out(conn, int(marked["start"]), int(marked["endExclusive"]) - 1, "all")
    elif command_id == "timeline.mark.clear":
        # The public contract names which endpoint is cleared; the native API
        # clears a track-domain pair, so preserve the other endpoint explicitly.
        marks = timeline_ops.get_mark_in_out(conn).get("marks") or {}
        kind = value["markType"]
        timeline_ops.clear_mark_in_out(conn, "all")
        if kind == "in" and marks.get("out") is not None:
            raw = timeline_ops.set_mark_in_out(conn, int(conn.timeline.GetStartFrame()), int(marks["out"]), "all")
        elif kind == "out" and marks.get("in") is not None:
            raw = timeline_ops.set_mark_in_out(conn, int(marks["in"]), int(conn.timeline.GetEndFrame()) - 1, "all")
        else:
            raw = {"cleared": True}
    elif command_id == "timeline.playhead.set":
        raw = timeline_ops.set_playhead(conn, _position(conn, value["position"]), return_details=True)
    elif command_id in {"timeline.set_start_tc", "timeline.start_tc"}:
        operation = value.get("operation")
        if command_id == "timeline.start_tc" and operation["kind"] == "get":
            raw = {"verified": True, "changed": False, "final_tc": conn.timeline.GetStartTimecode()}
        else:
            start = value["startTimecode"] if command_id == "timeline.set_start_tc" else operation["startTimecode"]
            raw = timeline_ops.set_start_timecode(conn, _start_timecode(start, conn.fps), return_details=True)
    elif command_id == "timeline.output_blanking.set":
        from . import output_blanking
        raw = output_blanking.write(conn, value)
    elif command_id == "timeline.settings_set":
        raw = _execution_phase(
            "timeline.setting_mutation",
            lambda: timeline_ops.set_timeline_setting(
                conn, value["key"], _native_timeline_setting_value(value["value"]),
                return_details=True,
            ),
        )
    elif command_id == "timeline.dolby.analyze":
        items = _item_rows(conn, value["timelineId"])
        requested_ids = list(value.get("timelineItemIds", []))
        by_public_id = {row["timelineItemId"]: row for row in items}
        selected = [by_public_id[item_id] for item_id in requested_ids if item_id in by_public_id]
        names = [row["item"].GetName() for row in selected]
        all_names = [row["item"].GetName() for row in items]
        if len(names) != len(requested_ids) or any(all_names.count(name) != 1 for name in names):
            raise ValueError("Dolby analysis cannot lower ambiguous Timeline item names.")
        raw = timeline_ops.analyze_dolby_vision(conn, names, blend_shots=value.get("blendShots", False), enable_project_controls=False)
        descriptors = raw.get("item_descriptors") if isinstance(raw, Mapping) else None
        descriptors_by_name = {
            descriptor.get("name"): descriptor
            for descriptor in descriptors or []
            if isinstance(descriptor, Mapping) and isinstance(descriptor.get("name"), str)
        }
        if not isinstance(descriptors, list) or len(descriptors_by_name) != len(selected) or any(
            descriptors_by_name.get(str(row["item"].GetName()), {}).get("start") != row["start"]
            or descriptors_by_name.get(str(row["item"].GetName()), {}).get("end") != row["end"]
            for row in selected
        ):
            raise ValueError("Dolby analysis readback did not match the exact requested native Timeline items.")
        analyzed_targets = [
            {
                "publicId": row["timelineItemId"], "nativeId": row["nativeId"],
                "name": str(row["item"].GetName()), "trackType": row["trackType"],
                "trackIndex": row["trackIndex"], "start": row["start"], "end": row["end"],
            }
            for row in selected
        ]
    elif command_id == "timeline.clip_color.batch":
        items = _item_rows(conn, value["timelineId"])
        by_public_id = {row["timelineItemId"]: row for row in items}
        color_results = []
        for update in value["updates"]:
            row = by_public_id.get(update["timelineItemId"])
            if row is None or any((
                row["trackType"] != update["trackType"],
                row["trackIndex"] != update["trackIndex"],
                row["start"] != update["recordStartFrame"],
                row["end"] != update["recordEndFrame"],
                row["name"] != update["name"],
            )):
                raise ValueError("Timeline clip-color target changed at the mutation boundary.")
            requested = update["color"]
            before_color = row["clipColor"] or None
            method_name = "ClearClipColor" if requested is None else "SetClipColor"
            method = getattr(row["item"], method_name, None)
            if not callable(method):
                raise ValueError(f"Timeline item does not expose {method_name}.")
            accepted = method() if requested is None else method(requested)
            if accepted is False:
                raise ValueError("DaVinci Resolve rejected a timeline clip-color change.")
            getter = getattr(row["item"], "GetClipColor", None)
            if not callable(getter):
                raise ValueError("Timeline clip-color readback is unavailable.")
            actual = str(getter() or "") or None
            if actual != requested:
                raise ValueError("Timeline clip-color readback did not match the request.")
            color_results.append({
                "clipId": update["timelineItemId"], "name": row["name"],
                "requestedColor": requested, "actualColor": actual,
                "changed": before_color != actual,
            })
        raw = {"clips": color_results, "verified": True}
    else:
        raise ValueError("Ordinary Timeline executor does not own this action.")
    _execution_phase("timeline.refresh", conn.refresh)
    after = _execution_phase(
        "timeline.after_state", lambda: (_state(conn, project_id, value) if action_id == "cutagent.action.timeline.output_blanking.set" else _state(conn, project_id))
    )
    after_fairlight = _fairlight_digest(conn) if command_id == "timeline.fairlight_preset.apply" else None
    return {
        "raw": _canonical(raw), "before": before, "after": after,
        "createdNativeId": documented_unique_id(created) if created else None,
        **({"analyzedTargets": analyzed_targets} if command_id == "timeline.dolby.analyze" else {}),
        **(
            {"fairlightReadback": {"before": before_fairlight, "after": after_fairlight}}
            if before_fairlight is not None
            else {}
        ),
    }


def _analysis_execute(context: Mapping[str, Any], command_id: str, value: Mapping[str, Any], prepared: Mapping[str, Any]) -> Mapping[str, Any]:
    if command_id != "timeline.dolby.analyze":
        raise ValueError("Analysis executor owns only Dolby analysis.")
    return _execute(context, command_id, value, prepared)


def _changed(result: Mapping[str, Any]) -> dict[str, Any]:
    before = str(result["before"]["revision"])
    after = str(result["after"]["revision"])
    return {"before": before, "after": after, "changed": before != after}


def _timeline_ref(state: Mapping[str, Any], timeline_id: str) -> dict[str, Any]:
    row = _row_by_id(list(state["timelines"]), timeline_id)
    return {"timelineId": timeline_id, "projectId": state["projectId"], "revision": row["revision"], "name": row["name"]}


def _project_result(_context: Mapping[str, Any], action_id: str, prepared: Mapping[str, Any], result: Any) -> Mapping[str, Any]:
    if not isinstance(result, Mapping):
        raise ValueError("Timeline result is unavailable.")
    value = prepared["lowering"]["normalizedInput"]
    before, after = result["before"], dict(result["after"])
    after["projectId"] = value["projectId"]
    revision = _changed(result)
    command = action_id.removeprefix("cutagent.action.")
    if command in {"timeline.create", "timeline.import", "timeline.duplicate"}:
        native_id = result.get("createdNativeId")
        if command == "timeline.duplicate":
            matches = [row for row in after["timelines"] if row["name"] == value["newName"] and row["timelineId"] not in {x["timelineId"] for x in before["timelines"]}]
            if len(matches) != 1: raise ValueError("Duplicated Timeline readback is ambiguous.")
            timeline_id = matches[0]["timelineId"]
        elif native_id:
            timeline_id = _digest("timeline_", {"projectId": value["projectId"], "nativeId": native_id})
        else:
            new_ids = {x["timelineId"] for x in after["timelines"]} - {x["timelineId"] for x in before["timelines"]}
            if len(new_ids) != 1: raise ValueError("Created Timeline readback is ambiguous.")
            timeline_id = new_ids.pop()
        return {"actionId": action_id, "timeline": _timeline_ref(after, timeline_id), "revisionChange": revision}
    if command == "timeline.delete":
        old = _row_by_id(list(before["timelines"]), value["timelineId"])
        active = after["active"]
        return {"actionId": action_id, "deletedTimeline": {"timelineId": old["timelineId"], "name": old["name"]}, "revisionChange": revision, "activeTimeline": ({"timelineId": active["timelineId"], "name": active["name"]} if active["timelineId"] else None)}
    if command == "timeline.rename":
        old = _row_by_id(list(before["timelines"]), value["timelineId"])
        return {"actionId": action_id, "timeline": _timeline_ref(after, value["timelineId"]), "previousName": old["name"], "revisionChange": revision}
    if command == "timeline.switch":
        old, active = before["active"], after["active"]
        return {"actionId": action_id, "previousTimeline": ({"timelineId": old["timelineId"], "name": old["name"]} if old["timelineId"] else None), "activeTimeline": {"timelineId": active["timelineId"], "name": active["name"]}, "revisionChange": revision}
    if command.startswith("timeline.mark."):
        marks = after["active"].get("marks") or {}
        marked = _range(int(marks["in"]), int(marks["out"]) + 1) if marks.get("in") is not None and marks.get("out") is not None else None
        return {"actionId": action_id, "markedRange": marked, "revisionChange": revision}
    if command == "timeline.playhead.set":
        return {"actionId": action_id, "position": _record(int(after["active"]["playhead"]["frame"])), "revisionChange": revision}
    if command in {"timeline.set_start_tc", "timeline.start_tc"}:
        start = {"domain": "timeline_record", "value": {"kind": "timecode", "value": str(after["active"]["startTimecode"])}}
        if command.endswith("set_start_tc"):
            return {"actionId": action_id, "startTimecode": start, "revisionChange": revision}
        if value["operation"]["kind"] == "get":
            return {"actionId": action_id, "operationResult": {"kind": "get", "startTimecode": start}}
        return {"actionId": action_id, "operationResult": {"kind": "set", "startTimecode": start, "revisionChange": revision}}
    if command == "timeline.output_blanking.set":
        return {"actionId": action_id, "state": after["active"]["outputBlanking"], "revisionChange": revision}
    if command == "timeline.settings_set":
        actual = after["active"]["settings"].get(value["key"])
        return {"actionId": action_id, "setting": {"key": value["key"], "value": _setting_value(actual)}, "revisionChange": revision}
    if command == "timeline.fairlight_preset.apply":
        return {"actionId": action_id, "presetName": value["presetName"], "revisionChange": revision}
    if command == "timeline.dolby.analyze":
        return {"actionId": action_id, "analyzedItemIds": list(value.get("timelineItemIds") or []), "revisionChange": revision}
    if command == "timeline.clip_color.batch":
        return {
            "actionId": action_id,
            "clips": list(result["raw"]["clips"]),
            "timelineRevision": str(after["revision"]),
        }
    raise ValueError("Timeline result projector does not own this action.")


def _playhead_readback_matches(result: Mapping[str, Any]) -> bool:
    raw = result.get("raw")
    before = result.get("before")
    after = result.get("after")
    if not isinstance(raw, Mapping) or not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return False
    before_active = before.get("active")
    after_active = after.get("active")
    before_playhead = before_active.get("playhead") if isinstance(before_active, Mapping) else None
    after_playhead = after_active.get("playhead") if isinstance(after_active, Mapping) else None
    frames = (
        raw.get("target_frame"), raw.get("pre_frame"), raw.get("final_frame"),
        before_playhead.get("frame") if isinstance(before_playhead, Mapping) else None,
        after_playhead.get("frame") if isinstance(after_playhead, Mapping) else None,
    )
    if any(not isinstance(frame, int) or isinstance(frame, bool) for frame in frames):
        return False
    target_frame, pre_frame, final_frame, before_frame, after_frame = frames
    return (
        raw.get("verified") is True
        and raw.get("changed") is (pre_frame != final_frame)
        and pre_frame == before_frame
        and final_frame == after_frame
        and abs(final_frame - target_frame) <= 1
    )


def _evidence(context: Mapping[str, Any], action_id: str, prepared: Mapping[str, Any], result: Any) -> Mapping[str, Any]:
    projected = _project_result(context, action_id, prepared, result)
    domain = prepared["domain"]
    command = action_id.removeprefix("cutagent.action.")
    value = prepared["lowering"]["normalizedInput"]
    before, after = result["before"], result["after"]
    changed = projected.get("revisionChange", projected.get("operationResult", {}).get("revisionChange", {})).get("changed") is True
    target_matched = changed
    if command == "timeline.clip_color.batch":
        target_matched = (
            result.get("raw", {}).get("verified") is True
            and len(projected["clips"]) == len(value["updates"])
            and all(
                observed["clipId"] == requested["timelineItemId"]
                and observed["requestedColor"] == requested["color"]
                and observed["actualColor"] == requested["color"]
                for observed, requested in zip(projected["clips"], value["updates"])
            )
        )
    if command == "timeline.create":
        target_matched = projected["timeline"]["name"] == value["name"]
    elif command == "timeline.delete":
        target_matched = all(row["timelineId"] != value["timelineId"] for row in after["timelines"])
    elif command == "timeline.duplicate":
        target_matched = projected["timeline"]["name"] == value["newName"]
    elif command == "timeline.import":
        target_matched = projected["timeline"]["timelineId"] not in {row["timelineId"] for row in before["timelines"]}
    elif command == "timeline.rename":
        target_matched = projected["timeline"]["name"] == value["newName"]
    elif command == "timeline.switch":
        target_matched = projected["activeTimeline"]["timelineId"] == value["timelineId"]
    elif command.startswith("timeline.mark."):
        if command == "timeline.mark.set":
            target_matched = projected["markedRange"] == value["range"]
        elif value["markType"] == "both":
            target_matched = projected["markedRange"] is None
        elif projected["markedRange"] is not None:
            target_matched = (
                projected["markedRange"]["start"] == int(after["active"]["startFrame"])
                if value["markType"] == "in"
                else projected["markedRange"]["endExclusive"] == int(after["active"]["endFrame"])
            )
    elif command == "timeline.playhead.set":
        target_matched = _playhead_readback_matches(result)
    elif command in {"timeline.set_start_tc", "timeline.start_tc"}:
        target_matched = result.get("raw", {}).get("verified") is True
    elif command == "timeline.output_blanking.set":
        actual = projected["state"]
        target_matched = (actual["blanking"] == value["operation"]["blanking"] and actual["useTimeline"] is not True) if value["operation"]["kind"] == "edges" else actual["useTimeline"] is value["operation"]["useTimeline"]
    elif command == "timeline.settings_set":
        target_matched = result.get("raw", {}).get("verified") is True
    elif command == "timeline.fairlight_preset.apply":
        target_matched = result.get("raw", {}).get("applied") is True
    if command == "timeline.dolby.analyze":
        target_matched = result.get("raw", {}).get("analyzed") is True and projected["analyzedItemIds"] == prepared["lowering"]["normalizedInput"].get("timelineItemIds", [])
    before_rows = {row["timelineId"]: row for row in before["timelines"]}
    after_rows = {row["timelineId"]: row for row in after["timelines"]}
    changed_ids = set()
    if command in {"timeline.delete", "timeline.rename", "timeline.switch"}:
        changed_ids.add(value["timelineId"])
    elif command == "timeline.duplicate":
        changed_ids.add(value["sourceTimelineId"])
    unaffected_timeline_ids = set(before_rows).intersection(after_rows) - changed_ids
    timeline_identities_preserved = all(
        before_rows[timeline_id]["nativeId"] == after_rows[timeline_id]["nativeId"]
        for timeline_id in unaffected_timeline_ids
    )
    before_structures = _canonical(before.get("timelineStructures", {}))
    after_structures = _canonical(after.get("timelineStructures", {}))
    if command == "timeline.clip_color.batch":
        selected_ids = {update["timelineItemId"] for update in value["updates"]}
        for structures in (before_structures, after_structures):
            for structure in structures.values():
                for item in structure.get("items", []):
                    if item.get("timelineItemId") in selected_ids:
                        item["clipColor"] = "<selected>"
    common_structure_ids = set(before_structures).intersection(after_structures)
    active_structure_preserved = all(
        before_structures[timeline_id].get("items")
        == after_structures[timeline_id].get("items")
        for timeline_id in common_structure_ids
    )
    linked_topology_preserved = all(
        [
            (row["nativeId"], row["linkedNativeIds"])
            for row in before_structures[timeline_id].get("items", [])
        ]
        == [
            (row["nativeId"], row["linkedNativeIds"])
            for row in after_structures[timeline_id].get("items", [])
        ]
        for timeline_id in common_structure_ids
    )
    track_state_preserved = True
    for timeline_id in common_structure_ids:
        before_tracks = before_structures[timeline_id].get("tracks", [])
        after_tracks = after_structures[timeline_id].get("tracks", [])
        if command in {"timeline.create", "timeline.switch"}:
            stable_track_keys = ("trackType", "trackIndex", "name", "subtype")
            before_tracks = [
                {key: row.get(key) for key in stable_track_keys}
                for row in before_tracks
            ]
            after_tracks = [
                {key: row.get(key) for key in stable_track_keys}
                for row in after_tracks
            ]
        if command == "timeline.fairlight_preset.apply":
            before_tracks = [row for row in before_tracks if row["trackType"] != "audio"]
            after_tracks = [row for row in after_tracks if row["trackType"] != "audio"]
        if before_tracks != after_tracks:
            track_state_preserved = False
            break
    if command == "timeline.fairlight_preset.apply":
        readback = result.get("fairlightReadback", {})
        target_matched = (
            result.get("raw", {}).get("applied") is True
            and isinstance(readback.get("before"), str)
            and isinstance(readback.get("after"), str)
            and readback["before"] != readback["after"]
        )
    if command == "timeline.output_blanking.set":
        prior = before["active"]["outputBlankingAll"]
        current = after["active"]["outputBlankingAll"]
        requested_item = value.get("timelineItemId")
        if requested_item is not None:
            def unaffected(snapshot):
                return {native_id: state for native_id, state in snapshot["items"].items()
                        if _digest("timeline_item_", {"timelineId": value["timelineId"], "nativeId": native_id}) != requested_item}
            blanking_preserved = prior["timeline"] == current["timeline"] and unaffected(prior) == unaffected(current)
        else:
            def own_states(snapshot):
                return {native_id: (dict(state) if state.get("available") is False else {key: state[key] for key in ("blanking", "use_timeline")})
                        for native_id, state in snapshot["items"].items()}
            blanking_preserved = own_states(prior) == own_states(current)
        active_structure_preserved = active_structure_preserved and blanking_preserved
    protected_truth = {
        "project_identity": before["projectNativeId"] == after["projectNativeId"],
        "timeline_identity": timeline_identities_preserved,
        "unaffected_tracks": track_state_preserved,
        "unaffected_items": active_structure_preserved,
        "linked_topology": linked_topology_preserved,
        "active_context": after["active"]["timelineId"] is not None,
    }
    protected = {name: protected_truth.get(name, False) for name in domain["protectedState"]}
    return {"targetMatched": target_matched, "authorizationBound": True, "modalities": list(domain["minimumEvidence"]), "protectedState": protected}


def _analysis_evidence(
    context: Mapping[str, Any], action_id: str,
    prepared: Mapping[str, Any], result: Any,
) -> Mapping[str, Any]:
    if action_id != "cutagent.action.timeline.dolby.analyze":
        raise ValueError("Analysis evidence owns only Dolby analysis.")
    evidence = dict(_evidence(context, action_id, prepared, result))
    requested = list(prepared["lowering"]["normalizedInput"]["timelineItemIds"])
    raw = result.get("raw", {}) if isinstance(result, Mapping) else {}
    analyzed_targets = result.get("analyzedTargets") if isinstance(result, Mapping) else None
    resolved_targets = prepared.get("domain", {}).get("resolvedTargets", [])
    expected_targets = [
        {
            "publicId": row.get("publicId"), "nativeId": row.get("nativeId"),
            "name": row.get("name"), "trackType": row.get("trackType"),
            "trackIndex": row.get("trackIndex"), "start": row.get("start"), "end": row.get("end"),
        }
        for row in resolved_targets
    ]
    before_items = {row["timelineItemId"]: row for row in result["before"]["active"]["items"]}
    after_items = {row["timelineItemId"]: row for row in result["after"]["active"]["items"]}
    evidence["targetMatched"] = (
        raw.get("analyzed") is True
        and analyzed_targets == expected_targets
        and [row.get("publicId") for row in analyzed_targets] == requested
        and all(item_id in before_items and after_items.get(item_id) == before_items[item_id] for item_id in requested)
    )
    evidence["modalities"] = [
        "revision_readback", "closed_target_readback", "protected_state_readback"
    ]
    return evidence


def _restore(_context: Mapping[str, Any], _action_id: str, prepared: Mapping[str, Any], _failure: BaseException) -> Mapping[str, Any]:
    checkpoint_id = str(prepared["domain"]["checkpointId"])
    conn = get_connection(require_project=True, require_timeline=False)
    restored = version_ops.restore_checkpoint(conn, checkpoint_id)
    domain = prepared["domain"]
    return {
        "checkpointId": checkpoint_id, "projectId": domain["projectId"],
        "timelineId": domain.get("timelineId"), "readbackMatched": restored.get("verified") is True,
        "protectedStatePreserved": restored.get("verified") is True,
        "protectedStateDigest": domain["privateCanonicalPreState"]["protectedStateDigest"],
    }


def timeline_ordinary_prepared_action_production_contribution() -> Mapping[str, TimelineVersionPreparedActionDescriptor]:
    descriptors = {}
    for action_id in TIMELINE_ORDINARY_PRODUCTION_ACTION_IDS:
        descriptors[action_id] = TimelineVersionPreparedActionDescriptor(
            descriptor=TIMELINE_VERSION_MUTATION_DESCRIPTORS[action_id],
            input_validator=_validate_input, authority_resolver=_authority,
            impact_builder=_impact,
            action_executor=_analysis_execute if action_id in TIMELINE_ANALYSIS_ACTION_IDS else _execute,
            evidence_reader=_analysis_evidence if action_id in TIMELINE_ANALYSIS_ACTION_IDS else _evidence,
            public_result_projector=_project_result,
            checkpoint_restorer=_restore,
            exact_checkpoint_pruner=_unsupported_production_execute,
            exact_timeline_sync_executor=_unsupported_production_execute,
        )
    return MappingProxyType(descriptors)
