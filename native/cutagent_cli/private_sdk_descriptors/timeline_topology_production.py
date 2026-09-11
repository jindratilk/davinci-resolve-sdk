"""Production lifecycle for exact track, linkage, and multi-target Timeline actions."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .._sdk_low_level_runtime import SDK_TIMELINE_PREPARED_ACTION_SCHEMAS
from ..commands import fusion as fusion_commands
from ..connection import ResolveConnection, get_connection
from ..core import fusion_text_ops, sdk_live_inspection, timeline_item_duration_db, timeline_layer_ops, timeline_ops, timeline_sync, version_ops
from ..errors import APICallFailed, ValidationError
from .timeline_version import TIMELINE_VERSION_MUTATION_DESCRIPTORS
from .timeline_version_prepared_action import timeline_version_prepared_action_descriptors
from .timeline_read_prepared_action import _digest as _public_digest


def timeline_action_input_schema(command_id: str) -> Mapping[str, Any] | None:
    row = SDK_TIMELINE_PREPARED_ACTION_SCHEMAS.get(f"cutagent.action.{command_id}")
    return row.get("input") if isinstance(row, Mapping) else None


def timeline_action_result_schema(action_id: str, _command_id: str) -> Mapping[str, Any] | None:
    row = SDK_TIMELINE_PREPARED_ACTION_SCHEMAS.get(action_id)
    return row.get("result") if isinstance(row, Mapping) else None


def _fusion_port(tool: Any, getter_name: str, id_key: str, port_name: str) -> Any | None:
    getter = getattr(tool, getter_name, None)
    if callable(getter):
        try:
            ports = getter() or {}
        except Exception:
            ports = {}
        rows = ports.items() if isinstance(ports, Mapping) else enumerate(ports, 1)
        for key, port in rows:
            attrs_getter = getattr(port, "GetAttrs", None)
            try:
                attrs = attrs_getter() or {} if callable(attrs_getter) else {}
            except Exception:
                attrs = {}
            if str(key) == port_name or attrs.get(id_key) == port_name:
                return port
    return getattr(tool, port_name, None)


def _ensure_exact_title_style_tool(comp: Any, text_tool: Any, input_name: str, style: Mapping[str, Any]) -> Any:
    requested_name = str(style["stylingToolName"])
    existing = fusion_text_ops.find_tool(comp, requested_name)
    if existing is not None:
        return existing
    adder = getattr(comp, "AddTool", None)
    if not callable(adder):
        raise APICallFailed("The requested exact Fusion title styling tool is unavailable.")
    style_tool = None
    for args in (("StyledTextCLS", -32768, -32768), ("StyledTextCLS",)):
        try:
            style_tool = adder(*args)
        except Exception:
            style_tool = None
        if style_tool:
            break
    if not style_tool:
        raise APICallFailed("The requested exact Fusion title styling tool could not be created.")
    if fusion_text_ops.tool_name(style_tool) != requested_name:
        setter = getattr(style_tool, "SetAttrs", None)
        try:
            renamed = setter({"TOOLS_Name": requested_name}) if callable(setter) else False
        except Exception:
            renamed = False
        if renamed is False or fusion_text_ops.tool_name(style_tool) != requested_name:
            raise APICallFailed("The created Fusion title styling tool lost its exact identity.")
    destination = _fusion_port(text_tool, "GetInputList", "INPS_ID", input_name)
    source = _fusion_port(style_tool, "GetOutputList", "OUTS_ID", "StyledText")
    connector = getattr(destination, "ConnectTo", None)
    if destination is None or source is None or not callable(connector):
        raise APICallFailed("The exact Fusion title styling connection is unavailable.")
    try:
        connected = connector(source)
    except Exception as exc:
        raise APICallFailed("The exact Fusion title styling connection failed.") from exc
    if connected is False:
        raise APICallFailed("The exact Fusion title styling connection was rejected.")
    return style_tool


TIMELINE_TOPOLOGY_ACTION_IDS = (
    "cutagent.action.timeline.compound_create",
    "cutagent.action.timeline.fusion_clip.create",
    "cutagent.action.timeline.fusion_composition.insert",
    "cutagent.action.timeline.import_into",
    "cutagent.action.timeline.insert_generator",
    "cutagent.action.timeline.insert_title",
    "cutagent.action.timeline.items.set_duration",
    "cutagent.action.timeline.layer.ensure_media",
    "cutagent.action.timeline.sync_clips",
    "cutagent.action.timeline.track.add",
    "cutagent.action.timeline.track.delete",
    "cutagent.action.timeline.track.disable",
    "cutagent.action.timeline.track.enable",
    "cutagent.action.timeline.track.lock",
    "cutagent.action.timeline.track.rename",
    "cutagent.action.timeline.track.unlock",
    "cutagent.action.timeline.voice_isolation.set",
)


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _frames(value: Mapping[str, Any]) -> int:
    inner = value.get("value")
    if not isinstance(inner, Mapping) or inner.get("kind") != "frames" or not isinstance(inner.get("value"), int):
        raise ValidationError("The prepared Timeline value must use exact frames.")
    return int(inner["value"])


def _record_ref(value: Mapping[str, Any]) -> str:
    inner = value.get("value")
    if not isinstance(inner, Mapping):
        raise ValidationError("The prepared Timeline record position is invalid.")
    return str(inner["value"]) if inner.get("kind") == "timecode" else f"{int(inner['value'])}f"


def _record_frame(conn: Any, value: Mapping[str, Any]) -> int:
    inner = value.get("value")
    if isinstance(inner, Mapping) and inner.get("kind") == "frames" and isinstance(inner.get("value"), int):
        # SDK timeline-record frame values are already absolute. Only textual
        # timecode needs conversion relative to the Timeline start frame.
        return int(inner["value"])
    return int(
        timeline_sync.parse_record_frame(
            _record_ref(value),
            float(conn.fps),
            int(getattr(conn, "start_frame", 0) or 0),
        )
    )


def _duration_updates(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    updates = value.get("updates")
    return list(updates) if isinstance(updates, list) else [value]


def _timeline_format_mismatches(
    expected_format: Mapping[str, Any],
    actual_format: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    mismatches: dict[str, dict[str, Any]] = {}
    for key in ("width", "height", "fps"):
        expected = expected_format.get(key)
        if expected is None:
            continue
        actual = actual_format.get(key)
        try:
            matches = (
                abs(float(actual) - float(expected)) < 0.001
                if key == "fps"
                else int(actual) == int(expected)
            )
        except (TypeError, ValueError):
            matches = False
        if not matches:
            mismatches[key] = {"expected": expected, "actual": actual}
    return mismatches


def _rows(snapshot: Mapping[str, Any]) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [(track, clip) for track in snapshot.get("tracks", ()) for clip in track.get("clips", ())]


def _clip_public(track: Mapping[str, Any], clip: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "timelineItemId": clip["id"],
        "name": str(clip.get("name") or "Timeline item"),
        "trackType": track["type"],
        "trackIndex": track["index"],
        "recordRange": {
            "domain": "timeline_record_range", "unit": "frames",
            "start": clip["recordRange"]["start"],
            "endExclusive": clip["recordRange"]["endExclusive"],
        },
    }
    if isinstance(clip.get("mediaPoolItemId"), str):
        value["mediaPoolItemId"] = clip["mediaPoolItemId"]
    return value


def _track_public(track: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "type": track["type"], "index": track["index"],
        "name": str(track.get("name") or f"{track['type'].title()} {track['index']}"),
        "enabled": track.get("enabled") is True,
        "locked": track.get("locked") is True,
    }
    if isinstance(track.get("subtype"), str) and track["subtype"]:
        value["subtype"] = track["subtype"]
    return value


class TimelineTopologyProductionAuthority:
    """One fixed production owner supplying all seven required callbacks."""

    def __init__(self) -> None:
        self._inspector = None

    def bind_private_timeline_inspector(self, inspector: Any) -> None:
        if not callable(inspector):
            raise TypeError("Timeline topology inspection callback must be callable.")
        self._inspector = inspector

    def invoke_admitted_handler(self, *_args: Any, **_kwargs: Any) -> Any:
        raise ValidationError("Timeline topology actions execute only through fixed lifecycle callbacks.")

    def validate_input(self, action_id: str, value: Any) -> Mapping[str, Any]:
        if action_id not in TIMELINE_TOPOLOGY_ACTION_IDS or not isinstance(value, Mapping):
            raise ValidationError("Timeline topology action input is unavailable.")
        command_id = action_id.removeprefix("cutagent.action.")
        schema = timeline_action_input_schema(command_id)
        errors = sorted(Draft202012Validator(schema).iter_errors(dict(value)), key=lambda item: list(item.path))
        if errors:
            raise ValidationError("Timeline topology action input violated its closed schema.")
        normalized = deepcopy(dict(value))
        if action_id in {
            "cutagent.action.timeline.fusion_composition.insert",
            "cutagent.action.timeline.insert_generator",
            "cutagent.action.timeline.insert_title",
        } and not all(key in normalized for key in ("trackIndex", "recordPosition", "duration")):
            raise ValidationError("Timeline insertion requires exact track, record position, and duration.")
        if action_id == "cutagent.action.timeline.insert_title" and normalized.get("authoredText") is not None:
            authored = normalized["authoredText"]
            if normalized.get("kind", "title") != "fusion_title":
                raise ValidationError("Authored title text requires kind fusion_title.")
            if (authored.get("uppercase") or authored.get("doubleSpaces")) and authored.get("role") != "header":
                raise ValidationError("Authored title header transforms require role header.")
            marker_count = authored["text"].count("**")
            style = authored.get("style")
            if style is None and marker_count:
                raise ValidationError("Markdown bold markers require an explicit authored title style binding.")
            if style is not None and (marker_count == 0 or marker_count % 2):
                raise ValidationError("Authored title markdown bold style requires balanced bold markers.")
            normalized_text = fusion_text_ops.normalize_role_text(
                authored["text"],
                role=authored.get("role"),
                uppercase=authored.get("uppercase", False),
                double_spaces=authored.get("doubleSpaces", False),
            )
            parsed_text = fusion_text_ops.parse_text_value(
                normalized_text,
                bold_style=style["boldStyle"] if style else "ExtraBold",
                styled=style is not None,
            )["clean_text"]
            if not 1 <= len(parsed_text) <= 8192:
                raise ValidationError(
                    "Authored title transformed text must contain 1 to 8192 Unicode characters."
                )
        if action_id == "cutagent.action.timeline.items.set_duration":
            updates = _duration_updates(normalized)
            item_ids = [update.get("timelineItemId") for update in updates]
            if (
                not updates
                or any(not isinstance(item_id, str) or not item_id for item_id in item_ids)
                or len(set(item_ids)) != len(item_ids)
            ):
                raise ValidationError("Timeline duration mutation requires unique exact timelineItemId values.")
        if action_id == "cutagent.action.timeline.sync_clips":
            sources = normalized["sourceItemIds"]
            if normalized.get("referenceItemId") is not None and normalized["referenceItemId"] not in sources:
                raise ValidationError("Timeline synchronization referenceItemId must be one of sourceItemIds.")
        return normalized

    def _inspect(self, value: Mapping[str, Any], *, phase: str = "current") -> Mapping[str, Any]:
        if not callable(self._inspector):
            raise ValidationError("Timeline topology action lacks fresh private inspection.")
        observed = self._inspector({
            "projectId": value["projectId"],
            "timelineId": value["timelineId"],
            "phase": phase,
        })
        snapshot = observed.get("snapshot") if isinstance(observed, Mapping) else None
        if not isinstance(snapshot, Mapping):
            raise ValidationError("Timeline topology inspection omitted its snapshot.")
        if snapshot.get("project", {}).get("id") != value["projectId"] or snapshot.get("timeline", {}).get("id") != value["timelineId"]:
            raise ValidationError("Timeline topology inspection changed exact project or timeline identity.")
        return snapshot

    @staticmethod
    def _bindings(context: Mapping[str, Any]) -> Mapping[str, Any]:
        bindings = context.get("privateBindings", {})
        topology = bindings.get("timelineTopology") if isinstance(bindings, Mapping) else None
        if not isinstance(topology, Mapping) or not isinstance(topology.get("snapshot"), Mapping) or not isinstance(topology.get("targets"), (list, tuple)):
            raise ValidationError("Timeline topology private target custody is unavailable.")
        return topology

    def resolve_authority(self, context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]) -> Mapping[str, Any]:
        topology = self._bindings(context)
        snapshot = self._inspect(value)
        timeline = context.get("timeline", {})
        project = context.get("project", {})
        if snapshot.get("revision") != timeline.get("timelineRevision") or value.get("revision") != snapshot.get("revision"):
            raise ValidationError("Timeline topology action revision is stale.")
        current_rows = {clip.get("id"): (track, clip) for track, clip in _rows(snapshot)}
        current_tracks = {(track.get("type"), track.get("index")): track for track in snapshot.get("tracks", ())}
        duration_roles: dict[str, str] = {}
        if action_id == "cutagent.action.timeline.items.set_duration":
            requested_ids = [update["timelineItemId"] for update in _duration_updates(value)]
            requested_set = set(requested_ids)
            if len(requested_set) != len(requested_ids) or any(item_id not in current_rows for item_id in requested_ids):
                raise ValidationError("Timeline duration requested identity set is stale or ambiguous.")
            closed_ids = set(requested_set)
            for item_id in requested_ids:
                linked_ids = current_rows[item_id][1].get("linkedItemIds", ())
                if any(
                    linked_id not in current_rows
                    or item_id not in current_rows[linked_id][1].get("linkedItemIds", ())
                    for linked_id in linked_ids
                ):
                    raise ValidationError("Timeline duration linked closure is no longer reciprocal.")
                closed_ids.update(linked_ids)
            bound_ids = {
                target.get("stableId")
                for target in topology["targets"]
                if target.get("kind") == "clip"
            }
            if bound_ids != closed_ids:
                raise ValidationError("Timeline duration target binding is not the exact requested and linked closure.")
            duration_roles = {
                item_id: "requested" if item_id in requested_set else "linked"
                for item_id in closed_ids
            }
        targets = []
        for target in topology["targets"]:
            kind = target.get("kind")
            stable_id = target.get("stableId")
            if kind == "clip":
                current = current_rows.get(stable_id)
                if current is None or current[0].get("type") != target.get("trackType") or current[0].get("index") != target.get("trackIndex"):
                    raise ValidationError("Timeline topology clip target changed before authorization.")
            elif kind == "track":
                current = current_tracks.get((target.get("trackType"), target.get("trackIndex")))
                if current is None or current.get("snapshotId") != stable_id:
                    raise ValidationError("Timeline topology track target changed before authorization.")
            elif kind == "timeline" and stable_id != snapshot.get("timeline", {}).get("id"):
                raise ValidationError("Timeline topology target changed before authorization.")
            elif kind == "media":
                matches = [row for row in topology.get("media", ()) if row.get("mediaPoolItemId") == stable_id]
                if len(matches) != 1 or not isinstance(matches[0].get("revision"), str):
                    raise ValidationError("Timeline topology media target lost private native custody.")
                targets.append({**dict(target), "revision": matches[0]["revision"]})
                continue
            targets.append({
                **dict(target),
                "revision": snapshot["revision"],
                **({"impactRole": duration_roles[stable_id]} if stable_id in duration_roles else {}),
            })
        operation_id = context.get("exactRequestBinding", {}).get("operationId")
        if not isinstance(operation_id, str):
            raise ValidationError("Timeline topology operation identity is unavailable.")
        checkpoint_id = f"chk_sdk_{hashlib.sha256(f'{operation_id}:{action_id}'.encode()).hexdigest()[:32]}"
        linked = sorted((clip["id"], tuple(sorted(clip.get("linkedItemIds", ())))) for _, clip in _rows(snapshot))
        return {
            "stale": False, "ambiguous": False, "complete": True, "broad": False,
            "closedComposition": True,
            "project": {"id": project["projectId"], "revision": project["projectRevision"]},
            "timeline": {"id": timeline["timelineId"], "revision": timeline["timelineRevision"]},
            "resolvedTargets": targets,
            "privatePreState": {
                "targetStableIds": sorted(target["stableId"] for target in targets),
                "protectedStateDigest": _digest(snapshot),
                "linkedTopologyDigest": _digest(linked),
                "activeContext": {"projectId": project["projectId"], "timelineId": timeline["timelineId"]},
            },
            "linkedTopologyComplete": True,
            "checkpointId": checkpoint_id,
            "checkpointProjectId": project["projectId"],
            "checkpointTimelineId": timeline["timelineId"],
            **({
                "syncPlacementPlanComplete": True,
                "privateExecutionProfile": "sdk_timeline_sync_exact_v1",
                "affectedTrackTypes": ["video", *([] if value.get("audioMode") == "none" else ["audio"])],
                "syncPlanDigest": _digest({"input": value, "media": topology.get("media", ())}),
            } if action_id == "cutagent.action.timeline.sync_clips" else {}),
        }

    def build_impact(self, context: Mapping[str, Any], _action_id: str, effect: Mapping[str, Any]) -> Mapping[str, Any]:
        base = context.get("mutationBase")
        if not isinstance(base, Mapping):
            raise ValidationError("Timeline topology mutation lacks its carrier mutation base.")
        return {
            **deepcopy(dict(base)),
            "status": "mutation", "effects": [dict(effect)], "complete": True,
            "closedComposition": True, "ambiguous": False, "broad": False,
            "executableStableTargetPrecondition": True,
            "verificationPolicy": {
                "minimumEvidence": ["readback"], "requireProtectedStatePreserved": True,
                "protectedTargetEvidence": "every_declared_target",
            },
        }

    def _assert_fresh_media(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], conn: Any,
    ) -> None:
        media = list(self._bindings(context).get("media", ()))
        if not media:
            return
        project_id = str(prepared["domain"]["projectId"])
        expected_digests = {row.get("poolDigest") for row in media}
        expected_revisions = {row.get("revision") for row in media}
        if len(expected_digests) != 1 or None in expected_digests or len(expected_revisions) != 1:
            raise ValidationError("Timeline topology Media Pool revision custody is incomplete.")
        deadline = int(time.time() * 1000) + sdk_live_inspection.SDK_LIVE_INSPECTION_MAX_DEADLINE_WINDOW_MS
        requested_native = {
            row.get("nativeId"): row.get("mediaPoolItemId") for row in media
            if isinstance(row.get("nativeId"), str)
            and isinstance(row.get("mediaPoolItemId"), str)
        }
        if len(requested_native) != len(media):
            raise ValidationError("Timeline topology Media Pool identity custody is ambiguous.")
        digest = hashlib.sha256()
        observed: dict[str, str] = {}
        for row in sdk_live_inspection._media_pool_rows(conn, deadline):
            sdk_live_inspection.validate_deadline(deadline)
            # Keep this byte-for-byte aligned with inspect_media_pool_page().
            # Selection is transient UI state and is intentionally excluded
            # from the durable Media Pool revision captured by the bridge.
            revision_row = (
                {key: value for key, value in row.items() if key != "selected"}
                if row.get("entry_kind") == "asset"
                else row
            )
            encoded = json.dumps(
                revision_row,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            native_id = row.get("native_id")
            if row.get("entry_kind") != "asset" or native_id not in requested_native:
                continue
            if native_id in observed:
                raise ValidationError("Timeline topology Media Pool identity became ambiguous.")
            observed[native_id] = _public_digest(
                "media_pool_item_", {"projectId": project_id, "nativeId": native_id},
            )
        sdk_live_inspection.validate_deadline(deadline)
        actual_digest = digest.hexdigest()
        actual_revision = _public_digest(
            "revision_", {"projectId": project_id, "poolDigest": actual_digest},
        )
        if actual_digest not in expected_digests or actual_revision not in expected_revisions:
            raise ValidationError("Timeline topology Media Pool changed after prepared capture.")
        if observed != requested_native:
            raise ValidationError("Timeline topology Media Pool identity changed before mutation.")

    @staticmethod
    def _assert_native_context(context: Mapping[str, Any], conn: Any) -> None:
        bindings = context.get("privateBindings", {})
        expected_project = bindings.get("nativeProjectId")
        expected_timeline = bindings.get("nativeTimelineId")
        project = getattr(conn, "project", None)
        timeline = getattr(conn, "timeline", None)
        actual_project = project.GetUniqueId() if project is not None and callable(getattr(project, "GetUniqueId", None)) else None
        actual_timeline = timeline.GetUniqueId() if timeline is not None and callable(getattr(timeline, "GetUniqueId", None)) else None
        if not expected_project or not expected_timeline or actual_project != expected_project or actual_timeline != expected_timeline:
            raise ValidationError("Timeline topology native project or timeline identity changed.")

    def _pre_mutation_connection(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any],
    ) -> Any:
        try:
            conn = get_connection(require_project=True, require_timeline=True)
            self._assert_native_context(context, conn)
            self._assert_fresh_media(context, prepared, conn)
            return conn
        except Exception as failure:
            # No checkpoint or target mutation has occurred at this boundary,
            # so recovery must not claim possible mutation or attempt restore.
            failure.possible_mutation = "none"
            raise

    def _native_items(self, context: Mapping[str, Any], public_ids: list[str]) -> list[Any]:
        topology = self._bindings(context)
        native_by_public = topology.get("timelineItemNativeIdByPublicId", {})
        expected = [native_by_public.get(value) for value in public_ids]
        if any(not value for value in expected):
            raise ValidationError("Timeline topology target lacks native identity custody.")
        conn = get_connection(require_project=True, require_timeline=True)
        self._assert_native_context(context, conn)
        found = {}
        for track_type in ("video", "audio", "subtitle"):
            count = int(conn.timeline.GetTrackCount(track_type) or 0)
            for index in range(1, count + 1):
                for item in conn.timeline.GetItemListInTrack(track_type, index) or []:
                    getter = getattr(item, "GetUniqueId", None)
                    native_id = str(getter() or "") if callable(getter) else ""
                    if native_id in expected:
                        if native_id in found:
                            raise ValidationError("Timeline topology native identity became ambiguous.")
                        found[native_id] = item
        if set(found) != set(expected):
            raise ValidationError("Timeline topology native target disappeared before execution.")
        return [found[value] for value in expected]

    def _ensure_checkpoint(self, context: Mapping[str, Any], action_id: str, prepared: Mapping[str, Any], conn: Any) -> None:
        checkpoint_id = prepared["domain"]["checkpointId"]
        existing = version_ops.get_checkpoint(checkpoint_id)
        expected_timeline = context.get("privateBindings", {}).get("nativeTimelineId")
        expected_session = context.get("session", {}).get("sessionId")
        if existing is not None:
            if existing.get("timeline_id") != expected_timeline or existing.get("session_id") != expected_session:
                raise ValidationError("Timeline topology checkpoint identity collided with unrelated state.")
            return
        created = version_ops.create_checkpoint(
            conn,
            label=f"SDK safety checkpoint: {action_id}",
            kind="before_prompt",
            session_id=expected_session,
            exact_checkpoint_id=checkpoint_id,
        )
        if created.get("id") != checkpoint_id or created.get("timeline_id") != expected_timeline:
            raise ValidationError("Timeline topology safety checkpoint lost exact identity.")

    @staticmethod
    def _author_title_item(item: Any, authored: Mapping[str, Any]) -> Mapping[str, Any]:
        comp = fusion_text_ops.get_fusion_comp_for_item(item)
        text_tool = fusion_text_ops.find_tool(comp, authored["toolName"]) if comp is not None else None
        if comp is None or text_tool is None:
            raise APICallFailed(
                "The requested exact Fusion title text tool is unavailable.",
                details={"toolName": authored["toolName"]},
            )
        style = authored.get("style")
        if style is not None:
            _ensure_exact_title_style_tool(comp, text_tool, authored["inputName"], style)
        update = fusion_text_ops.set_text_on_item(
            item,
            text=authored["text"],
            role=authored.get("role"),
            explicit_tool=authored["toolName"],
            input_names=[authored["inputName"]],
            uppercase=authored.get("uppercase", False),
            double_spaces=authored.get("doubleSpaces", False),
            bold_style=style["boldStyle"] if style else "ExtraBold",
            styled=style is not None,
            cls_tool_candidates=[style["stylingToolName"]] if style else [],
        )
        readback = update.get("readback", {})
        exact = bool(
            update.get("verified") is True
            and update.get("tool_selected") == authored["toolName"]
            and update.get("input_applied") == authored["inputName"]
            and readback.get("value") == update.get("clean_text")
        )
        if style is not None:
            exact = bool(
                exact
                and update.get("cls_applied") is True
                and readback.get("cls_tool") == style["stylingToolName"]
                and readback.get("cls_text") == update.get("clean_text")
                and readback.get("cls_value") is not None
            )
        if not exact:
            raise APICallFailed(
                "Exact authored Fusion title text/style did not verify before placement.",
                details={"authoredText": dict(authored), "update": update},
            )
        return {
            "requestedText": authored["text"],
            "text": update["clean_text"],
            "toolName": authored["toolName"],
            "inputName": authored["inputName"],
            "styled": style is not None,
            "style": ({**dict(style), "verified": True} if style else None),
            "styleText": readback.get("cls_text") if style else None,
            "styleValue": readback.get("cls_value") if style else None,
            "verified": True,
        }

    @staticmethod
    def _read_authored_title_item(item: Any, expected: Mapping[str, Any]) -> Mapping[str, Any]:
        comp = fusion_text_ops.get_fusion_comp_for_item(item)
        tool = fusion_text_ops.find_tool(comp, expected["toolName"]) if comp is not None else None
        text = (
            fusion_text_ops.serialize_value(fusion_text_ops.read_tool_input(tool, expected["inputName"]))
            if tool is not None else None
        )
        style_value = None
        style_text = None
        style_tool = None
        if expected.get("styled") and comp is not None:
            style_tool = fusion_text_ops.find_tool(comp, expected["style"]["stylingToolName"])
            if style_tool is not None:
                style_text = fusion_text_ops.serialize_value(
                    fusion_text_ops.read_tool_input(style_tool, "Text")
                )
                style_value = fusion_text_ops.serialize_value(
                    fusion_text_ops.read_tool_input(style_tool, "CharacterLevelStyling")
                )
        verified = bool(
            tool is not None
            and fusion_text_ops.tool_name(tool) == expected["toolName"]
            and text == expected["text"]
            and (
                not expected.get("styled")
                or (
                    style_tool is not None
                    and fusion_text_ops.tool_name(style_tool) == expected["style"]["stylingToolName"]
                    and style_text == expected["styleText"]
                    and style_value == expected["styleValue"]
                )
            )
        )
        if not verified:
            raise APICallFailed(
                "Exact authored Fusion title text/style did not survive durable placement.",
                details={
                    "expected": dict(expected),
                    "readback": {
                        "text": text,
                        "toolName": fusion_text_ops.tool_name(tool) if tool is not None else None,
                        "styleToolName": fusion_text_ops.tool_name(style_tool) if style_tool is not None else None,
                        "styleText": style_text,
                        "styleValue": style_value,
                    },
                },
            )
        result = {
            key: expected[key]
            for key in ("requestedText", "text", "toolName", "inputName", "styled", "verified")
        }
        if expected.get("style") is not None:
            result["style"] = dict(expected["style"])
        return result

    @classmethod
    def _insert_precisely(cls, conn: Any, command_id: str, value: Mapping[str, Any]) -> Mapping[str, Any]:
        record_frame = _record_frame(conn, value["recordPosition"])
        duration_frames = _frames(value["duration"])
        if duration_frames <= 0:
            raise ValidationError("Exact Timeline insertion duration must be greater than zero.")
        target_timeline_name = str(conn.timeline.GetName() or "")
        if not target_timeline_name:
            raise APICallFailed("Exact Timeline insertion lost the active Timeline name.")
        try:
            target_playhead = timeline_ops.get_playhead(conn)
        except Exception:
            target_playhead = None
        if command_id == "timeline.fusion_composition.insert":
            method_name, arguments, holder_kind = "InsertFusionCompositionIntoTimeline", (), "fusion"
            requested_name = "Fusion Composition"
        elif command_id == "timeline.insert_generator":
            kind = value.get("kind", "generator")
            method_name = {
                "generator": "InsertGeneratorIntoTimeline",
                "fusion_generator": "InsertFusionGeneratorIntoTimeline",
                "ofx_generator": "InsertOFXGeneratorIntoTimeline",
            }[kind]
            arguments, holder_kind, requested_name = (value["name"],), kind, value["name"]
        else:
            kind = value.get("kind", "title")
            method_name = "InsertFusionTitleIntoTimeline" if kind == "fusion_title" else "InsertTitleIntoTimeline"
            arguments, holder_kind, requested_name = (value["name"],), kind, value["name"]
        scratch_name = fusion_commands._unique_validate_scratch_timeline_name(conn)
        scratch_created = False
        cleanup = None
        try:
            timeline_format = fusion_commands._current_timeline_format(conn)
            # The creation owner reads inherited values before writing, so an
            # exact project-format match performs no redundant SetSetting calls
            # while a custom target format applies only its real differences.
            timeline_ops.create_timeline(
                conn,
                scratch_name,
                width=timeline_format.get("width"),
                height=timeline_format.get("height"),
                fps=timeline_format.get("fps"),
            )
            scratch_created = True
            conn.refresh()
            scratch_format = fusion_commands._current_timeline_format(conn)
            format_mismatches = _timeline_format_mismatches(timeline_format, scratch_format)
            if format_mismatches:
                raise APICallFailed(
                    "Exact Timeline insertion scratch Timeline did not match the target format.",
                    details={"mismatches": format_mismatches},
                )
            if str(conn.timeline.GetName() or "") != scratch_name or fusion_commands._enumerated_video_items(conn):
                raise APICallFailed("Exact Timeline insertion scratch Timeline did not open empty.")
            scratch_start = fusion_commands._connection_start_frame(conn)
            timeline_ops.set_playhead(conn, fusion_commands._absolute_record_frame_ref(conn, scratch_start))
            inserter = getattr(conn.timeline, method_name, None)
            if not callable(inserter):
                raise APICallFailed(f"{method_name} is unavailable for exact Timeline insertion.")
            item = inserter(*arguments)
            if not item:
                raise APICallFailed("DaVinci Resolve did not create the requested Timeline item.")
            authored_proof = None
            if command_id == "timeline.insert_title" and value.get("authoredText") is not None:
                authored_proof = cls._author_title_item(item, value["authoredText"])
            staging = fusion_commands._timeline_item_readback(item)
            if staging.get("start") is None or staging.get("duration") is None or staging.get("track_index") is None:
                raise APICallFailed("Inserted Timeline item omitted exact native placement readback.")
            staging["db_start_candidates"] = fusion_commands._project_db_start_candidates(conn, int(staging["start"]))
            timeline_ops.switch_timeline(conn, name=target_timeline_name)
            moved = fusion_commands._move_native_precise_holder_via_db(
                conn,
                timeline_name=target_timeline_name,
                source_timeline_name=scratch_name,
                staging_readback=staging,
                target_track=int(value["trackIndex"]),
                target_record_frame=record_frame,
                target_duration_frames=duration_frames,
                clip_name=str(staging.get("name") or requested_name),
                holder=requested_name,
                holder_kind=holder_kind,
                require_fusion_tools=authored_proof is not None,
            )
            fresh = ResolveConnection.get()
            fresh.connect()
            cleanup = fusion_commands._cleanup_native_precise_scratch_timeline(
                fresh,
                target_timeline_name=target_timeline_name,
                scratch_timeline_name=scratch_name,
                target_playhead=target_playhead,
            )
            if not cleanup.get("ok"):
                raise APICallFailed("Exact Timeline insertion scratch cleanup did not verify.", details={"cleanup": cleanup})
            if authored_proof is not None:
                final_row = fusion_commands._unique_enumerated_video_item(
                    fresh,
                    track_index=int(value["trackIndex"]),
                    start=record_frame,
                    duration=duration_frames,
                    name=str(staging.get("name") or requested_name),
                )
                authored_proof = cls._read_authored_title_item(final_row["item"], authored_proof)
            return {**moved, "scratch_cleanup": cleanup, "authored_text": authored_proof}
        except Exception:
            if scratch_created and not (isinstance(cleanup, Mapping) and cleanup.get("ok")):
                try:
                    fresh = ResolveConnection.get()
                    fresh.connect()
                    fusion_commands._cleanup_native_precise_scratch_timeline(
                        fresh,
                        target_timeline_name=target_timeline_name,
                        scratch_timeline_name=scratch_name,
                        target_playhead=target_playhead,
                    )
                except Exception:
                    pass
            raise

    def execute(self, context: Mapping[str, Any], command_id: str, value: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        conn = self._pre_mutation_connection(context, prepared)
        action_id = f"cutagent.action.{command_id}"
        self._ensure_checkpoint(context, action_id, prepared, conn)
        if command_id == "timeline.compound_create":
            target_ids = [row["stableId"] for row in prepared["domain"]["resolvedTargets"] if row["kind"] == "clip"]
            items = self._native_items(context, target_ids)
            info = {key: value[key] for key in ("name",) if value.get(key)}
            if value.get("startTimecode"):
                info["startTimecode"] = _record_ref(value["startTimecode"])
            result = conn.timeline.CreateCompoundClip(items, info) if info else conn.timeline.CreateCompoundClip(items)
            if not result:
                raise APICallFailed("Failed to create exact prepared compound clip.")
            return {"created": True}
        if command_id == "timeline.fusion_clip.create":
            result = conn.timeline.CreateFusionClip(self._native_items(context, list(value["timelineItemIds"])))
            if not result:
                raise APICallFailed("Failed to create exact prepared Fusion clip.")
            return {"created": True}
        if command_id in {"timeline.fusion_composition.insert", "timeline.insert_generator", "timeline.insert_title"}:
            return self._insert_precisely(conn, command_id, value)
        if command_id == "timeline.import_into":
            record = self._bindings(context).get("inputFile")
            path = Path(record.get("absolutePath", "")) if isinstance(record, Mapping) else None
            stat = path.lstat() if path else None
            if not stat or not path.is_file() or path.is_symlink() or tuple(map(str, (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns))) != (record["device"], record["inode"], record["size"], record["mtimeNs"]) or _file_digest(path) != record.get("sha256"):
                raise ValidationError("Timeline import source changed after prepared capture.")
            try:
                return timeline_ops.import_into_timeline(conn, str(path), offset_tc=_record_ref(value["recordOffset"]) if value.get("recordOffset") else None)
            finally:
                path.unlink(missing_ok=True)
        if command_id == "timeline.items.set_duration":
            native_by_public = self._bindings(context)["timelineItemNativeIdByPublicId"]
            targets = {
                row["stableId"]: row
                for row in prepared["domain"]["resolvedTargets"]
                if row["kind"] == "clip"
            }
            updates = _duration_updates(value)
            if "updates" not in value:
                update = updates[0]
                target = targets[update["timelineItemId"]]
                return timeline_item_duration_db.set_timeline_item_duration(
                    conn, item_id=native_by_public[update["timelineItemId"]],
                    track_type=target["trackType"], track_index=target["trackIndex"],
                    duration=f"{_frames(update['duration'])}f" if update.get("duration") else None,
                    target_end_frame=_record_ref(update["targetEnd"]) if update.get("targetEnd") else None,
                    allow_overlap=update.get("allowOverlap", False),
                    enforce_source_bounds=update.get("enforceSourceBounds", True),
                )
            entries = []
            for update in updates:
                target = targets[update["timelineItemId"]]
                entries.append({
                    "item_id": native_by_public[update["timelineItemId"]],
                    "track_type": target["trackType"],
                    "track_index": target["trackIndex"],
                    "duration": f"{_frames(update['duration'])}f" if update.get("duration") else None,
                    "target_end_frame": _record_ref(update["targetEnd"]) if update.get("targetEnd") else None,
                    "allow_overlap": update.get("allowOverlap", False),
                    "enforce_source_bounds": update.get("enforceSourceBounds", True),
                })
            return timeline_item_duration_db.set_timeline_item_durations(conn, entries)
        if command_id == "timeline.layer.ensure_media":
            media = next(row for row in self._bindings(context)["media"] if row["mediaPoolItemId"] == value["mediaPoolItemId"])
            return timeline_layer_ops.ensure_media_layer(
                conn, media["nativeId"], value["trackIndex"],
                _record_frame(conn, value["recordPosition"]), _frames(value["duration"]),
                extend_gap_frames=_frames(value["duration"]) if value.get("gapPolicy") == "extend" else 0,
                allow_insert=value.get("allowInsert", True), allow_extend=value.get("allowExtend", True),
            )
        if command_id == "timeline.stereo_convert":
            return timeline_ops.convert_timeline_to_stereo(conn)
        if command_id == "timeline.track.add":
            return {"changed": timeline_ops.add_track(conn, value["trackType"], subtype=value.get("subtype"), index=value.get("index"))}
        if command_id == "timeline.track.delete":
            return timeline_ops.delete_track(conn, value["trackType"], value["index"])
        if command_id == "timeline.track.rename":
            return {"changed": timeline_ops.rename_track(conn, value["trackType"], value["index"], value["name"])}
        if command_id in {"timeline.track.enable", "timeline.track.disable"}:
            return timeline_ops.set_track_enabled(conn, value["trackType"], value["index"], command_id.endswith("enable"), return_details=True)
        if command_id in {"timeline.track.lock", "timeline.track.unlock"}:
            return timeline_ops.set_track_locked(conn, value["trackType"], value["index"], command_id.endswith("lock"), return_details=True)
        if command_id == "timeline.voice_isolation.set":
            return timeline_ops.set_timeline_voice_isolation(conn, value["trackIndex"], enabled=value.get("enabled"), amount=value.get("amount"))
        raise ValidationError(f"Timeline topology executor does not own {action_id}.")

    def execute_sync(self, context: Mapping[str, Any], value: Mapping[str, Any], _prepared: Mapping[str, Any]) -> Any:
        conn = self._pre_mutation_connection(context, _prepared)
        self._ensure_checkpoint(context, "cutagent.action.timeline.sync_clips", _prepared, conn)
        media = {row["mediaPoolItemId"]: row for row in self._bindings(context)["media"]}
        sources = [f"source_{index}=media_id:{media[item_id]['nativeId']}" for index, item_id in enumerate(value["sourceItemIds"], 1)]
        reference = value.get("referenceItemId")
        reference_label = f"source_{value['sourceItemIds'].index(reference) + 1}" if reference in value["sourceItemIds"] else None
        mode = value["syncMode"]
        if mode not in {"waveform", "timecode"}:
            raise ValidationError("The exact prepared Timeline synchronization mode is not implemented by CutAgent CLI.")
        current_name = conn.timeline.GetName()
        return timeline_sync.execute_sync(
            conn, source_specs=sources, timeline_name=current_name, create_timeline=False,
            sync_mode=mode, reference_label=reference_label,
            audio_mode={"linked": "reference", "separate": "all", "none": "none"}[value.get("audioMode", "linked")],
            record_frame=_record_ref(value["recordPosition"]) if value.get("recordPosition") else None,
            subframe_mode="round", use_timecode_prior=False, apply=True,
        )

    def read_evidence(self, _context: Mapping[str, Any], action_id: str, prepared: Mapping[str, Any], result: Any) -> Mapping[str, Any]:
        value = prepared["lowering"]["normalizedInput"]
        after = self._inspect(value, phase="verify")
        before = self._bindings(_context)["snapshot"]
        before_rows = {clip["id"]: (track, clip) for track, clip in _rows(before)}
        after_rows = {clip["id"]: (track, clip) for track, clip in _rows(after)}
        affected = {row["stableId"] for row in prepared["domain"]["resolvedTargets"] if row["kind"] == "clip"}
        input_value = prepared["lowering"]["normalizedInput"]
        command_id = action_id.removeprefix("cutagent.action.")
        if command_id == "timeline.track.delete":
            affected.update(clip["id"] for track, clip in _rows(before) if track["type"] == input_value["trackType"] and track["index"] == input_value["index"])
        def expected_track_coordinate(track: Mapping[str, Any]) -> tuple[str, int]:
            expected_index = int(track["index"])
            if command_id == "timeline.track.add" and track["type"] == input_value["trackType"]:
                inserted_at = input_value.get("index")
                if inserted_at is not None and expected_index >= inserted_at:
                    expected_index += 1
            elif command_id == "timeline.track.delete" and track["type"] == input_value["trackType"] and expected_index > input_value["index"]:
                expected_index -= 1
            return str(track["type"]), expected_index
        unaffected_before = {key: row for key, row in before_rows.items() if key not in affected}
        protected_items = all(key in after_rows and {
            "track": expected_track_coordinate(row[0]), "range": row[1].get("recordRange"),
            "name": row[1].get("name"), "media": row[1].get("mediaPoolItemId"), "links": sorted(row[1].get("linkedItemIds", ()))
        } == {
            "track": (after_rows[key][0]["type"], after_rows[key][0]["index"]), "range": after_rows[key][1].get("recordRange"),
            "name": after_rows[key][1].get("name"), "media": after_rows[key][1].get("mediaPoolItemId"), "links": sorted(after_rows[key][1].get("linkedItemIds", ()))
        } for key, row in unaffected_before.items())
        before_tracks = before.get("tracks", ())
        after_tracks = after.get("tracks", ())
        coordinate = (
            ("audio", input_value.get("trackIndex"))
            if command_id == "timeline.voice_isolation.set"
            else (input_value.get("trackType"), input_value.get("index"))
        )
        if command_id == "timeline.track.add":
            target_matched = len(after_tracks) == len(before_tracks) + 1 and any(
                track["type"] == input_value["trackType"]
                and (input_value.get("index") is None or track["index"] == input_value["index"])
                for track in after_tracks
            )
        elif command_id == "timeline.track.delete":
            target_matched = len(after_tracks) == len(before_tracks) - 1
        elif command_id == "timeline.track.rename":
            target_matched = any(track["type"] == coordinate[0] and track["index"] == coordinate[1] and track.get("name") == input_value["name"] for track in after_tracks)
        elif command_id in {"timeline.track.enable", "timeline.track.disable"}:
            expected = command_id.endswith("enable")
            target_matched = any(track["type"] == coordinate[0] and track["index"] == coordinate[1] and track.get("enabled") is expected for track in after_tracks)
        elif command_id in {"timeline.track.lock", "timeline.track.unlock"}:
            expected = command_id.endswith("lock")
            target_matched = any(track["type"] == coordinate[0] and track["index"] == coordinate[1] and track.get("locked") is expected for track in after_tracks)
        elif command_id == "timeline.items.set_duration":
            conn = get_connection(require_timeline=True)
            target_matched = all(
                (target := after_rows.get(update["timelineItemId"])) is not None
                and (
                    target[1]["recordRange"]["endExclusive"] - target[1]["recordRange"]["start"] == _frames(update["duration"])
                    if update.get("duration") is not None
                    else target[1]["recordRange"]["endExclusive"] == _record_frame(conn, update["targetEnd"])
                )
                for update in _duration_updates(input_value)
            )
        elif command_id in {"timeline.fusion_composition.insert", "timeline.insert_generator", "timeline.insert_title"}:
            created = [(track, clip) for track, clip in _rows(after) if clip["id"] not in before_rows]
            requested_start = _record_frame(get_connection(require_timeline=True), input_value["recordPosition"])
            target_matched = len(created) == 1 and (
                created[0][0]["type"] == "video"
                and created[0][0]["index"] == input_value["trackIndex"]
                and created[0][1]["recordRange"]["endExclusive"] - created[0][1]["recordRange"]["start"] == _frames(input_value["duration"])
                and created[0][1]["recordRange"]["start"] == requested_start
            )
            if command_id == "timeline.insert_title" and input_value.get("authoredText") is not None:
                target_matched = bool(
                    target_matched
                    and isinstance(result, Mapping)
                    and result.get("authored_text", {}).get("verified") is True
                )
        elif command_id == "timeline.layer.ensure_media":
            requested_start = _record_frame(get_connection(require_timeline=True), input_value["recordPosition"])
            requested_duration = _frames(input_value["duration"])
            target_matched = any(
                track["type"] == "video"
                and track["index"] == input_value["trackIndex"]
                and clip.get("mediaPoolItemId") == input_value["mediaPoolItemId"]
                and clip["recordRange"]["start"] <= requested_start
                and clip["recordRange"]["endExclusive"] >= requested_start + requested_duration
                for track, clip in _rows(after)
            )
        elif command_id == "timeline.import_into":
            created_ids = set(after_rows) - set(before_rows)
            created = [after_rows[item_id] for item_id in created_ids]
            offset = input_value.get("recordOffset")
            offset_frame = _record_frame(get_connection(require_timeline=True), offset) if offset else None
            target_matched = bool(
                isinstance(result, Mapping)
                and result.get("imported") is True
                and created
                and (offset_frame is None or min(int(clip["recordRange"]["start"]) for _track, clip in created) == offset_frame)
            )
        elif command_id == "timeline.sync_clips":
            created_ids = set(after_rows) - set(before_rows)
            plan = result.get("plan") if isinstance(result, Mapping) else None
            placements = plan.get("placements") if isinstance(plan, Mapping) else None
            source_by_label = {
                f"source_{index}": item_id
                for index, item_id in enumerate(input_value["sourceItemIds"], 1)
            }
            target_matched = bool(
                result.get("verification", {}).get("status") == "verified"
                and plan.get("sync", {}).get("mode") == input_value["syncMode"]
                and isinstance(placements, list)
                and placements
                and all(
                    any(
                        item_id in created_ids
                        and clip.get("mediaPoolItemId") == source_by_label.get(placement.get("label"))
                        and track.get("type") == placement.get("track_type")
                        and track.get("index") == placement.get("track_index")
                        and clip.get("recordRange", {}).get("start") == placement.get("record_frame")
                        for item_id, (track, clip) in after_rows.items()
                    )
                    for placement in placements
                )
            )
        elif command_id == "timeline.stereo_convert":
            raise ValidationError(
                "Timeline stereo conversion has no authoritative post-state readback."
            )
        elif command_id == "timeline.voice_isolation.set":
            expected_enabled = input_value.get("enabled")
            expected_amount = input_value.get("amount")
            target_matched = isinstance(result, Mapping) and (
                expected_enabled is None or result.get("isEnabled", result.get("enabled")) is expected_enabled
            ) and (expected_amount is None or result.get("amount") == expected_amount)
        else:
            target_matched = len(set(after_rows) - set(before_rows)) == 1
        target_matched = bool(target_matched)
        target_track_ids = {row["stableId"] for row in prepared["domain"]["resolvedTargets"] if row["kind"] == "track"}
        protected_tracks = True
        for track in before_tracks:
            if track.get("snapshotId") in target_track_ids:
                continue
            expected_type, expected_index = expected_track_coordinate(track)
            matches = [candidate for candidate in after_tracks if candidate["type"] == expected_type and candidate["index"] == expected_index]
            if len(matches) != 1 or any(matches[0].get(key) != track.get(key) for key in ("name", "enabled", "locked")):
                protected_tracks = False
                break
        descriptor = TIMELINE_VERSION_MUTATION_DESCRIPTORS[action_id]
        protected = {name: True for name in descriptor.protected_state}
        protected.update({"project_identity": after.get("project", {}).get("id") == before.get("project", {}).get("id"), "timeline_identity": after.get("timeline", {}).get("id") == before.get("timeline", {}).get("id"), "unaffected_tracks": protected_tracks, "unaffected_items": protected_items, "linked_topology": protected_items, "active_context": after.get("project", {}).get("id") == before.get("project", {}).get("id") and after.get("timeline", {}).get("id") == before.get("timeline", {}).get("id")})
        if isinstance(result, dict):
            result["_verifiedAfterSnapshot"] = deepcopy(after)
        return {
            "targetMatched": target_matched,
            "authorizationBound": True,
            "modalities": list(descriptor.minimum_evidence),
            "protectedState": protected,
            "afterSnapshot": after,
        }

    def project_result(self, _context: Mapping[str, Any], action_id: str, prepared: Mapping[str, Any], _result: Any) -> Mapping[str, Any]:
        before = self._bindings(_context)["snapshot"]
        after = _result.pop("_verifiedAfterSnapshot", None) if isinstance(_result, dict) else None
        if not isinstance(after, Mapping):
            raise ValidationError("Timeline topology projection lacks its verified after-snapshot.")
        before_ids = {clip["id"] for _, clip in _rows(before)}
        after_rows = _rows(after)
        changed = {"before": before["revision"], "after": after["revision"], "changed": before["revision"] != after["revision"]}
        command_id = action_id.removeprefix("cutagent.action.")
        if command_id.startswith("timeline.track."):
            payload = {"tracks": [_track_public(track) for track in after.get("tracks", ())], "revisionChange": changed}
        elif command_id == "timeline.voice_isolation.set":
            state = timeline_ops.get_timeline_voice_isolation(get_connection(require_timeline=True), prepared["lowering"]["normalizedInput"]["trackIndex"])
            payload = {"trackIndex": state.get("track", prepared["lowering"]["normalizedInput"]["trackIndex"]), "enabled": bool(state.get("isEnabled", state.get("enabled"))), "amount": int(state.get("amount", 0)), "revisionChange": changed}
        elif command_id == "timeline.stereo_convert":
            payload = {"timeline": {"timelineId": after["timeline"]["id"], "projectId": after["project"]["id"], "revision": after["revision"], "name": after["timeline"]["name"]}, "revisionChange": changed}
        elif command_id == "timeline.layer.ensure_media":
            value = prepared["lowering"]["normalizedInput"]
            requested_start = _record_frame(get_connection(require_timeline=True), value["recordPosition"])
            requested_end = requested_start + _frames(value["duration"])
            matching = [
                (track, clip) for track, clip in after_rows
                if track.get("type") == "video"
                and track.get("index") == value["trackIndex"]
                and clip.get("mediaPoolItemId") == value["mediaPoolItemId"]
                and clip.get("recordRange", {}).get("start", requested_end) <= requested_start
                and clip.get("recordRange", {}).get("endExclusive", requested_start) >= requested_end
            ]
            if len(matching) != 1:
                raise ValidationError("Timeline media-layer result did not identify one exact covered item.")
            payload = {"item": _clip_public(*matching[0]), "revisionChange": changed}
        else:
            created = [(track, clip) for track, clip in after_rows if clip["id"] not in before_ids]
            if command_id in {"timeline.import_into", "timeline.items.set_duration", "timeline.sync_clips"}:
                if command_id == "timeline.items.set_duration":
                    requested = [
                        update["timelineItemId"]
                        for update in _duration_updates(prepared["lowering"]["normalizedInput"])
                    ]
                    by_id = {clip["id"]: (track, clip) for track, clip in after_rows}
                    created = [by_id[target] for target in requested if target in by_id]
                payload = {"items": [_clip_public(track, clip) for track, clip in created], "revisionChange": changed}
            else:
                if len(created) != 1:
                    raise ValidationError("Timeline topology result did not identify exactly one created item.")
                payload = {"item": _clip_public(*created[0]), "revisionChange": changed}
                if command_id == "timeline.insert_title" and prepared["lowering"]["normalizedInput"].get("authoredText") is not None:
                    authored = _result.get("authored_text") if isinstance(_result, Mapping) else None
                    if not isinstance(authored, Mapping) or authored.get("verified") is not True:
                        raise ValidationError("Authored title result lacks durable text/style proof.")
                    payload["authoredText"] = dict(authored)
        result = {"actionId": action_id, **payload}
        schema = timeline_action_result_schema(action_id, command_id)
        if list(Draft202012Validator(schema).iter_errors(result)):
            raise ValidationError("Timeline topology public result violated its closed schema.")
        return result

    def restore_checkpoint(self, context: Mapping[str, Any], _action_id: str, prepared: Mapping[str, Any], _failure: BaseException) -> Mapping[str, Any]:
        domain = prepared["domain"]
        checkpoint_id = domain["checkpointId"]
        conn = get_connection(require_project=True, require_timeline=True)
        result = version_ops.restore_checkpoint(conn, checkpoint_id, session_id=context.get("session", {}).get("sessionId"))
        restored = result.get("verified") is True and result.get("reopened") is True
        snapshot = self._inspect(prepared["lowering"]["normalizedInput"], phase="verify") if restored else None
        expected_digest = domain.get("privateCanonicalPreState", {}).get("protectedStateDigest")
        readback_matched = bool(snapshot is not None and _digest(snapshot) == expected_digest)
        return {
            "checkpointId": checkpoint_id,
            "projectId": domain.get("projectId"),
            "timelineId": domain.get("timelineId"),
            "readbackMatched": readback_matched,
            "protectedStatePreserved": readback_matched,
            "protectedStateDigest": expected_digest if readback_matched else None,
        }


def timeline_topology_prepared_action_packet() -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    authority = TimelineTopologyProductionAuthority()
    all_descriptors = timeline_version_prepared_action_descriptors(
        input_validator=authority.validate_input,
        authority_resolver=authority.resolve_authority,
        impact_builder=authority.build_impact,
        action_executor=authority.execute,
        evidence_reader=authority.read_evidence,
        public_result_projector=authority.project_result,
        checkpoint_restorer=authority.restore_checkpoint,
        exact_checkpoint_pruner=lambda *_args: None,
        exact_timeline_sync_executor=authority.execute_sync,
    )
    descriptors = MappingProxyType({action_id: all_descriptors[action_id] for action_id in TIMELINE_TOPOLOGY_ACTION_IDS})
    authorities = MappingProxyType({action_id: authority for action_id in TIMELINE_TOPOLOGY_ACTION_IDS})
    return descriptors, authorities


__all__ = ["TIMELINE_TOPOLOGY_ACTION_IDS", "TimelineTopologyProductionAuthority", "timeline_topology_prepared_action_packet"]
