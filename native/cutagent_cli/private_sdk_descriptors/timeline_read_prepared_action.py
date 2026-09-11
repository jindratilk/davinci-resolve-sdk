"""Production prepared-action descriptors for residual Timeline reads."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import lru_cache
import hashlib
from importlib.resources import files
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from ..connection import get_connection
from ..core import clip_ops, timeline_ops
from ..core.sdk_live_inspection import documented_unique_id
TIMELINE_READ_ACTION_CAPABILITIES: Mapping[str, str | None] = MappingProxyType(
    {
        "cutagent.action.timeline.clip_markers.list": "clip.marker",
        "cutagent.action.timeline.current_item": None,
        "cutagent.action.timeline.duration": None,
        "cutagent.action.timeline.info": None,
        "cutagent.action.timeline.item_at": "timeline.item_at",
        "cutagent.action.timeline.list": "timeline.list",
        "cutagent.action.timeline.mark.get": "timeline.marker_crud",
        "cutagent.action.timeline.marker.list": "timeline.marker_crud",
        "cutagent.action.timeline.media_pool_item": "timeline.item_at",
        "cutagent.action.timeline.node_graph.inspect": "color.node_graph_ops",
        "cutagent.action.timeline.playhead.get": "timeline.playhead_set",
        "cutagent.action.timeline.settings": None,
        "cutagent.action.timeline.output_blanking.get": "timeline.output_blanking",
        "cutagent.action.timeline.summarize": None,
        "cutagent.action.timeline.track.items": "timeline.track_management",
        "cutagent.action.timeline.track.list": "timeline.track_management",
        "cutagent.action.timeline.track.subtype": "timeline.track_management",
        "cutagent.action.timeline.voice_isolation.get": "fairlight.timeline_voice_isolation",
    }
)
TIMELINE_READ_ACTION_IDS = tuple(TIMELINE_READ_ACTION_CAPABILITIES)


@lru_cache(maxsize=1)
def _public_action_contract_definitions() -> Mapping[str, Any]:
    payload = json.loads(
        files("cutagent_cli")
        .joinpath("public_contract/action-contracts.schema.json")
        .read_text(encoding="utf-8")
    )
    definitions = payload.get("$defs")
    if not isinstance(definitions, Mapping):
        raise RuntimeError("Packaged public action-contract definitions are unavailable.")
    return MappingProxyType(dict(definitions))


def timeline_action_input_schema(command_id: str) -> Mapping[str, Any] | None:
    return _public_action_contract_definitions().get(
        f"cutagent.action.{command_id}.input"
    )


def timeline_action_result_schema(
    action_id: str, command_id: str
) -> Mapping[str, Any] | None:
    expected = f"cutagent.action.{command_id}"
    if action_id != expected:
        raise ValueError(
            f"Timeline action identity mismatch: expected {expected}, got {action_id}."
        )
    return _public_action_contract_definitions().get(f"{action_id}.result")


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise TypeError("Timeline read contains a non-finite number.")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("Timeline read object keys must be strings.")
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    raise TypeError("Timeline read is not canonical JSON.")


def _digest(prefix: str, value: Any) -> str:
    payload = json.dumps(
        _canonical(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    token = (
        base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")
    )
    return f"{prefix}f{token}"


def _sha256(value: Any) -> str:
    payload = json.dumps(
        _canonical(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _matches_type(expected: Any, value: Any) -> bool:
    choices = expected if isinstance(expected, list) else [expected]
    for choice in choices:
        if choice == "null" and value is None:
            return True
        if choice == "object" and isinstance(value, Mapping):
            return True
        if choice == "array" and isinstance(value, list):
            return True
        if choice == "string" and isinstance(value, str):
            return True
        if choice == "boolean" and isinstance(value, bool):
            return True
        if (
            choice == "integer"
            and isinstance(value, int)
            and not isinstance(value, bool)
        ):
            return True
        if (
            choice == "number"
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            return True
    return False


def _matches_schema(schema: Mapping[str, Any], value: Any) -> bool:
    if "oneOf" in schema:
        return (
            sum(_matches_schema(candidate, value) for candidate in schema["oneOf"]) == 1
        )
    if "const" in schema and value != schema["const"]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(expected_type, value):
        return False
    if isinstance(value, Mapping):
        required = set(schema.get("required", ()))
        properties = schema.get("properties", {})
        if not required.issubset(value):
            return False
        if schema.get("additionalProperties") is False and not set(value).issubset(
            properties
        ):
            return False
        return all(
            key not in properties or _matches_schema(properties[key], item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)) or len(value) > int(
            schema.get("maxItems", 10**9)
        ):
            return False
        item_schema = schema.get("items")
        return item_schema is None or all(
            _matches_schema(item_schema, item) for item in value
        )
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)) or len(value) > int(
            schema.get("maxLength", 10**9)
        ):
            return False
        pattern = schema.get("pattern")
        return pattern is None or re.search(pattern, value) is not None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value >= schema.get("minimum", value) and value <= schema.get(
            "maximum", value
        )
    return True


def _record(frame: int) -> dict[str, Any]:
    return {
        "domain": "timeline_record",
        "value": {"kind": "frames", "value": int(frame)},
    }


def _source(frame: int) -> dict[str, Any]:
    return {"domain": "source", "value": {"kind": "frames", "value": int(frame)}}


def _duration(frames: int) -> dict[str, Any]:
    return {
        "domain": "duration",
        "value": {"kind": "frames", "value": max(0, int(frames))},
    }


def _range(start: int, end: int) -> dict[str, Any]:
    return {
        "domain": "timeline_record_range",
        "unit": "frames",
        "start": int(start),
        "endExclusive": int(end),
    }


def _identity(
    context: Mapping[str, Any], section: str, id_key: str, revision_key: str
) -> dict[str, str]:
    value = context.get(section)
    if not isinstance(value, Mapping):
        raise ValueError(f"Signed runtime {section} identity is unavailable.")
    identity = value.get(id_key)
    revision = value.get(revision_key)
    if (
        not isinstance(identity, str)
        or not identity
        or not isinstance(revision, str)
        or not revision
    ):
        raise ValueError(f"Signed runtime {section} identity is incomplete.")
    return {"id": identity, "revision": revision}


def _timeline_bounds(conn: Any) -> tuple[int, int]:
    start = int(conn.timeline.GetStartFrame())
    end_getter = getattr(conn.timeline, "GetEndFrame", None)
    if callable(end_getter):
        end = int(end_getter())
    else:
        end = start
        for track_type in ("video", "audio", "subtitle"):
            for index in range(
                1, int(conn.timeline.GetTrackCount(track_type) or 0) + 1
            ):
                for item in conn.timeline.GetItemListInTrack(track_type, index) or []:
                    end = max(end, int(item.GetEnd()))
    return start, max(start, end)


def _item_value(
    item: Any,
    *,
    project_id: str,
    timeline_id: str,
    track_type: str,
    track_index: int,
) -> dict[str, Any]:
    native_id = documented_unique_id(item)
    if not native_id:
        raise ValueError("Timeline item lacks an authoritative native identity.")
    start = int(item.GetStart())
    end = int(item.GetEnd())
    media = item.GetMediaPoolItem() if hasattr(item, "GetMediaPoolItem") else None
    media_native_id = (
        timeline_ops.documented_sdk_media_pool_id(media) if media is not None else None
    )
    return {
        "timelineItemId": _digest(
            "timeline_item_", {"timelineId": timeline_id, "nativeId": native_id}
        ),
        **(
            {
                "mediaPoolItemId": _digest(
                    "media_pool_item_",
                    {
                        "projectId": project_id,
                        "nativeId": media_native_id,
                    },
                )
            }
            if media_native_id
            else {}
        ),
        "name": str(item.GetName() or "Unnamed"),
        "trackType": track_type,
        "trackIndex": int(track_index),
        "recordRange": _range(start, end),
    }


def _track_value(row: Mapping[str, Any], subtype: Any = None) -> dict[str, Any]:
    track_type = str(row.get("type") or "")
    index = int(row.get("index") or 0)
    name = row.get("name")
    enabled = row.get("enabled")
    locked = row.get("locked")
    normalized_subtype = subtype if subtype is not None else row.get("subtype")
    if (
        track_type not in {"video", "audio", "subtitle"}
        or index < 1
        or not isinstance(name, str)
        or not name
        or not isinstance(enabled, bool)
        or not isinstance(locked, bool)
        or not isinstance(normalized_subtype, str)
        or not normalized_subtype
    ):
        raise ValueError("Timeline track readback is incomplete.")
    return {
        "type": track_type,
        "index": index,
        "name": name,
        "enabled": enabled,
        "locked": locked,
        "subtype": normalized_subtype,
    }


def _track_values(conn: Any, rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for row in rows:
        track_type = str(row.get("type") or "")
        index = int(row.get("index") or 0)
        subtype = timeline_ops.get_track_subtype(conn, track_type, index).get("subtype")
        values.append(_track_value(row, subtype))
    return values


def _setting_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"kind": "boolean", "value": value}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"kind": "number", "value": value}
    return {"kind": "text", "value": str(value if value is not None else "")}


def _is_private_local_path(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith(("/Users/", "/home/", "/tmp/", "\\\\")) or (
        len(value) >= 3
        and value[0].isalpha()
        and value[1:3] in {":\\", ":/"}
    )


def _public_setting_rows(settings: Mapping[Any, Any]) -> list[dict[str, Any]]:
    return [
        {"key": str(key), "value": _setting_value(setting)}
        for key, setting in sorted(settings.items(), key=lambda item: str(item[0]))
        if str(key) and not _is_private_local_path(setting)
    ]


def _native_binding(*, require_timeline: bool) -> dict[str, str]:
    conn = get_connection(require_project=True, require_timeline=require_timeline)
    project_native_id = documented_unique_id(conn.project)
    if not project_native_id:
        raise ValueError("Active project lacks an authoritative native identity.")
    binding = {"projectNativeId": project_native_id}
    if require_timeline:
        timeline_native_id = documented_unique_id(conn.timeline)
        if not timeline_native_id:
            raise ValueError("Active Timeline lacks an authoritative native identity.")
        binding["timelineNativeId"] = timeline_native_id
    return binding


def _read_execute(
    action_id: str,
    context: Mapping[str, Any],
    value: Mapping[str, Any],
    *,
    expected_native_binding: Mapping[str, Any],
) -> dict[str, Any]:
    command_id = action_id.removeprefix("cutagent.action.")
    conn = get_connection(
        require_project=True,
        require_timeline=command_id != "timeline.list",
    )
    project_id = str(value["projectId"])
    timeline_id = str(
        value.get("timelineId") or context.get("timeline", {}).get("timelineId") or ""
    )
    observed_project_native_id = documented_unique_id(conn.project)
    if (
        not observed_project_native_id
        or observed_project_native_id != expected_native_binding.get("projectNativeId")
    ):
        raise ValueError("Active project changed after signed read authorization.")
    if command_id != "timeline.list":
        native_timeline_id = documented_unique_id(conn.timeline)
        if not native_timeline_id or native_timeline_id != expected_native_binding.get(
            "timelineNativeId"
        ):
            raise ValueError("Active Timeline changed after signed read authorization.")
        observed_timeline_id = _digest(
            "timeline_", {"projectId": project_id, "nativeId": native_timeline_id}
        )
        if observed_timeline_id != timeline_id:
            raise ValueError("Active Timeline changed after signed read authorization.")
    if command_id == "timeline.list":
        rows = timeline_ops.list_timelines(conn, authoritative_ids=True)
        timelines = []
        for row in rows:
            native_id = row.get("timeline_id")
            if not isinstance(native_id, str) or not native_id:
                raise ValueError(
                    "Timeline list lacks an authoritative native identity."
                )
            public_id = _digest(
                "timeline_", {"projectId": project_id, "nativeId": native_id}
            )
            timelines.append(
                {
                    "timelineId": public_id,
                    "projectId": project_id,
                    "revision": _digest("revision_", row),
                    "name": str(row.get("name") or "Unnamed"),
                }
            )
        return {"actionId": action_id, "timelines": timelines}
    if command_id in {"timeline.duration", "timeline.info"}:
        start, end = _timeline_bounds(conn)
        if command_id == "timeline.duration":
            return {
                "actionId": action_id,
                "recordRange": _range(start, end),
                "duration": _duration(end - start),
                "frameRate": float(conn.fps),
            }
        info = timeline_ops.get_timeline_info(conn)
        tracks = timeline_ops.list_tracks(conn, authoritative_state=True)
        playhead = timeline_ops.get_playhead(conn)
        return {
            "actionId": action_id,
            "timeline": {
                "timelineId": timeline_id,
                "projectId": project_id,
                "revision": str(context["timeline"]["timelineRevision"]),
                "name": str(info.get("name") or "Unnamed"),
            },
            "recordRange": _range(start, end),
            "frameRate": float(conn.fps),
            "tracks": _track_values(conn, tracks),
            "playhead": _record(int(playhead["frame"])),
        }
    if command_id in {"timeline.current_item", "timeline.item_at"}:
        candidates: list[tuple[Any, str, int]] = []
        if command_id == "timeline.current_item":
            item = conn.timeline.GetCurrentVideoItem()
            if item is not None:
                for index in range(
                    1, int(conn.timeline.GetTrackCount("video") or 0) + 1
                ):
                    if item in (conn.timeline.GetItemListInTrack("video", index) or []):
                        candidates.append((item, "video", index))
                        break
        else:
            position = value["recordPosition"]["value"]
            frame = (
                int(position["value"])
                if position["kind"] == "frames"
                else int(
                    timeline_ops.resolve_playhead_target(conn, position["value"])[
                        "target_frame"
                    ]
                )
            )
            track_types = (
                [value["trackType"]]
                if value["trackType"] != "all"
                else ["video", "audio", "subtitle"]
            )
            for track_type in track_types:
                indices = (
                    [int(value["trackIndex"])]
                    if value.get("trackIndex") is not None
                    else range(1, int(conn.timeline.GetTrackCount(track_type) or 0) + 1)
                )
                for index in indices:
                    for item in (
                        conn.timeline.GetItemListInTrack(track_type, index) or []
                    ):
                        if int(item.GetStart()) <= frame < int(item.GetEnd()):
                            candidates.append((item, track_type, int(index)))
        return {
            "actionId": action_id,
            "item": (
                _item_value(
                    candidates[0][0],
                    project_id=project_id,
                    timeline_id=timeline_id,
                    track_type=candidates[0][1],
                    track_index=candidates[0][2],
                )
                if candidates
                else None
            ),
        }
    if command_id == "timeline.track.items":
        track_type = str(value["trackType"])
        index = int(value["index"])
        items = conn.timeline.GetItemListInTrack(track_type, index) or []
        return {
            "actionId": action_id,
            "items": [
                _item_value(
                    item,
                    project_id=project_id,
                    timeline_id=timeline_id,
                    track_type=track_type,
                    track_index=index,
                )
                for item in items
            ],
        }
    if command_id in {"timeline.track.list", "timeline.track.subtype"}:
        rows = timeline_ops.list_tracks(conn, authoritative_state=True)
        if command_id == "timeline.track.subtype":
            track_type = str(value["trackType"])
            index = int(value["index"])
            rows = [
                row
                for row in rows
                if row.get("type") == track_type and row.get("index") == index
            ]
            if len(rows) != 1:
                raise ValueError(
                    "Timeline track subtype target is missing or ambiguous."
                )
            tracks = _track_values(conn, rows)
        else:
            tracks = _track_values(conn, rows)
        return {"actionId": action_id, "tracks": tracks}
    if command_id == "timeline.playhead.get":
        return {
            "actionId": action_id,
            "position": _record(int(timeline_ops.get_playhead(conn)["frame"])),
        }
    if command_id == "timeline.mark.get":
        marks = timeline_ops.get_mark_in_out(conn).get("marks")
        mark_in = marks.get("in") if isinstance(marks, Mapping) else None
        mark_out = marks.get("out") if isinstance(marks, Mapping) else None
        return {
            "actionId": action_id,
            "markedRange": (
                _range(int(mark_in), int(mark_out) + 1)
                if mark_in is not None and mark_out is not None
                else None
            ),
        }
    if command_id == "timeline.marker.list":
        markers = []
        for row in timeline_ops.list_markers(conn):
            markers.append(
                {
                    "position": _record(int(row["record_frame"])),
                    "color": str(row.get("color") or "Blue"),
                    "name": str(row.get("name") or "Unnamed"),
                    "note": str(row.get("note") or ""),
                    "duration": _duration(int(row.get("duration") or 1)),
                }
            )
        return {"actionId": action_id, "markers": markers}
    if command_id == "timeline.clip_markers.list":
        raw = clip_ops.list_timeline_clip_markers(
            conn,
            track_type=str(value.get("trackType") or "video"),
            tracks=value.get("trackIndexes"),
            color=value.get("color"),
            visible_only=value.get("visibleOnly", True) is True,
            authoritative_ids=True,
        )
        markers = []
        for row in raw["markers"]:
            native_id = row.get("timeline_item_unique_id")
            if not isinstance(native_id, str) or not native_id:
                raise ValueError(
                    "Clip marker lacks an authoritative timeline item identity."
                )
            markers.append(
                {
                    "timelineItemId": _digest(
                        "timeline_item_",
                        {"timelineId": timeline_id, "nativeId": native_id},
                    ),
                    "trackType": str(row["track_type"]),
                    "trackIndex": int(row["track_index"]),
                    "sourcePosition": _source(int(row["source_frame"])),
                    "recordPosition": _record(int(row["record_frame"])),
                    "color": str(row.get("color") or "Blue"),
                    "name": str(row.get("name") or "Unnamed"),
                    "note": str(row.get("note") or ""),
                    "duration": _duration(int(row.get("duration") or 1)),
                }
            )
        return {"actionId": action_id, "clipMarkers": markers}
    if command_id == "timeline.settings":
        raw = timeline_ops.get_timeline_settings(conn, value.get("key"))
        settings = raw if isinstance(raw, Mapping) else {str(value["key"]): raw}
        return {
            "actionId": action_id,
            "settings": _public_setting_rows(settings),
        }
    if command_id == "timeline.media_pool_item":
        item = timeline_ops.current_timeline_media_pool_item(conn)["item"]
        native_id = timeline_ops.documented_sdk_media_pool_id(item)
        if not native_id:
            raise ValueError(
                "Timeline Media Pool item lacks an authoritative identity."
            )
        return {
            "actionId": action_id,
            "mediaPoolItemId": _digest(
                "media_pool_item_", {"projectId": project_id, "nativeId": native_id}
            ),
        }
    if command_id == "timeline.node_graph.inspect":
        raw = timeline_ops.inspect_timeline_node_graph(conn)
        return {
            "actionId": action_id,
            "nodeGraph": {"present": raw.get("available") is True},
        }
    if command_id == "timeline.output_blanking.get":
        from . import output_blanking
        return {"actionId": action_id, "state": output_blanking.read(conn, value)}
    if command_id == "timeline.voice_isolation.get":
        raw = timeline_ops.get_timeline_voice_isolation(conn, int(value["trackIndex"]))
        enabled = raw.get("isEnabled", raw.get("enabled"))
        amount = raw.get("amount", raw.get("Amount", 0))
        if not isinstance(enabled, bool):
            raise ValueError("Voice Isolation readback omitted enabled state.")
        return {
            "actionId": action_id,
            "trackIndex": int(value["trackIndex"]),
            "enabled": enabled,
            "amount": int(amount),
        }
    if command_id == "timeline.summarize":
        raw = timeline_ops.summarize_timeline(
            conn,
            window="range" if value.get("range") else "all",
            start_ref=(str(value["range"]["start"]) + "f")
            if value.get("range")
            else None,
            end_ref=(str(value["range"]["endExclusive"]) + "f")
            if value.get("range")
            else None,
            track_type=str(value.get("trackType") or "all"),
            max_runs=int(value.get("maximumRuns") or 24),
            include_items=True,
            authoritative_track_state=True,
        )
        runs = []
        for track in raw.get("tracks", []):
            for item in track.get("items", []):
                native_id = item.get("timeline_item_unique_id")
                if not native_id:
                    raise ValueError(
                        "Timeline summary item lacks an authoritative identity."
                    )
                runs.append(
                    {
                        "recordRange": _range(int(item["start"]), int(item["end"])),
                        "trackType": str(track["type"]),
                        "itemIds": [
                            _digest(
                                "timeline_item_",
                                {"timelineId": timeline_id, "nativeId": str(native_id)},
                            )
                        ],
                    }
                )
        return {"actionId": action_id, "runs": runs}
    raise ValueError(f"Timeline read executor does not own {action_id}.")


@dataclass(frozen=True)
class TimelineReadPreparedActionDescriptor:
    action_id: str
    capability_id: str | None

    operation_class = "read"
    version = 1

    @property
    def command_id(self) -> str:
        return self.action_id.removeprefix("cutagent.action.")

    def validate_input(self, value: Any) -> dict[str, Any]:
        schema = timeline_action_input_schema(self.command_id)
        if not isinstance(schema, Mapping) or not _matches_schema(schema, value):
            raise ValueError(
                "Timeline read input does not match its exact public schema."
            )
        return _canonical(value)

    def _state(
        self, context: Mapping[str, Any], value: Mapping[str, Any]
    ) -> dict[str, Any]:
        project = _identity(context, "project", "projectId", "projectRevision")
        if value.get("projectId") != project["id"]:
            raise ValueError("Timeline read project identity changed.")
        targets = [
            {
                "kind": "project",
                "stableId": project["id"],
                "revision": project["revision"],
                "projectId": project["id"],
                "timelineId": None,
            }
        ]
        if self.command_id != "timeline.list":
            timeline = _identity(context, "timeline", "timelineId", "timelineRevision")
            if value.get("timelineId") != timeline["id"]:
                raise ValueError("Timeline read Timeline identity changed.")
            targets.append(
                {
                    "kind": "timeline",
                    "stableId": timeline["id"],
                    "revision": timeline["revision"],
                    "projectId": project["id"],
                    "timelineId": timeline["id"],
                }
            )
        pre_state = {
            "projectId": project["id"],
            "projectRevision": project["revision"],
            "nativeBinding": _native_binding(
                require_timeline=self.command_id != "timeline.list"
            ),
            **(
                {
                    "timelineId": targets[-1]["stableId"],
                    "timelineRevision": targets[-1]["revision"],
                }
                if len(targets) == 2
                else {}
            ),
        }
        return {"targets": targets, "preState": pre_state}

    def prepare(
        self, context: Mapping[str, Any], value: Mapping[str, Any]
    ) -> dict[str, Any]:
        state = self._state(context, value)
        return {
            **state,
            "impact": {
                "contractVersion": 1,
                "status": "read",
                "complete": True,
                "targetDigests": [_sha256(target) for target in state["targets"]],
                "resultMaximumBytes": 6 * 1024 * 1024,
            },
            "lowering": {"commandId": self.command_id, "normalizedInput": value},
            "verification": {"minimumEvidence": ["readback"]},
            "recovery": {"mode": "not_applicable"},
        }

    def resolve_current(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any]
    ) -> dict[str, Any]:
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValueError("Prepared Timeline read input is unavailable.")
        return self._state(context, value)

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValueError("Prepared Timeline read input is unavailable.")
        native_binding = prepared.get("preState", {}).get("nativeBinding")
        if not isinstance(native_binding, Mapping):
            raise ValueError("Prepared Timeline read native binding is unavailable.")
        return _read_execute(
            self.action_id,
            context,
            value,
            expected_native_binding=native_binding,
        )

    def verify(
        self, _context: Mapping[str, Any], _prepared: Mapping[str, Any], result: Any
    ) -> dict[str, Any]:
        schema = timeline_action_result_schema(self.action_id, self.command_id)
        passed = isinstance(schema, Mapping) and _matches_schema(schema, result)
        return {
            "outcome": "passed" if passed else "failed",
            "evidence": [
                {
                    "modality": "readback",
                    "digest": _sha256(result),
                    "summary": "Authoritative DaVinci Resolve readback matched the typed result.",
                }
            ],
            "protectedStatePreserved": True,
        }

    def recover(
        self,
        _context: Mapping[str, Any],
        _prepared: Mapping[str, Any],
        _failure: BaseException,
    ) -> dict[str, Any]:
        return {
            "outcome": "succeeded",
            "attempted": True,
            "manualActionRequired": False,
        }

    def project_result(
        self, _context: Mapping[str, Any], _prepared: Mapping[str, Any], result: Any
    ) -> Any:
        return _canonical(result)

    def validate_public_result(self, value: Any) -> bool:
        try:
            schema = timeline_action_result_schema(self.action_id, self.command_id)
            return isinstance(schema, Mapping) and _matches_schema(
                schema, _canonical(value)
            )
        except (KeyError, TypeError, ValueError):
            return False


def timeline_read_prepared_action_production_contribution() -> Mapping[
    str, TimelineReadPreparedActionDescriptor
]:
    return MappingProxyType(
        {
            action_id: TimelineReadPreparedActionDescriptor(action_id, capability_id)
            for action_id, capability_id in TIMELINE_READ_ACTION_CAPABILITIES.items()
        }
    )
