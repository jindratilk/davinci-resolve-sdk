"""Exact multi-clip enable/disable prepared actions."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from ..connection import get_connection
from ..errors import APICallFailed, ValidationError


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"


def _bindings(context: Mapping[str, Any]) -> tuple[Mapping[str, str], Mapping[str, Any]]:
    private = context.get("privateBindings")
    timeline = context.get("timeline")
    native = private.get("privateTimelineItemNativeIds") if isinstance(private, Mapping) else None
    if not isinstance(native, Mapping) or not isinstance(timeline, Mapping):
        raise ValidationError("Bulk clip-state private target custody is unavailable.")
    if any(not isinstance(key, str) or not isinstance(value, str) or not key or not value for key, value in native.items()):
        raise ValidationError("Bulk clip-state private target custody is malformed.")
    return native, timeline


def _call(value: Any, *args: Any) -> Any:
    return value(*args) if callable(value) else None


def _scan(context: Mapping[str, Any], prepared_input: Mapping[str, Any]) -> tuple[Any, list[dict[str, Any]], str]:
    native_by_public, timeline = _bindings(context)
    if (timeline.get("timelineId") != prepared_input["timelineId"]
            or timeline.get("timelineRevision") != prepared_input["timelineRevision"]):
        raise ValidationError("Bulk clip-state timeline binding is stale.")
    expected_native = [native_by_public.get(target["id"]) for target in prepared_input["targets"]]
    if any(not value for value in expected_native) or len(set(expected_native)) != len(expected_native):
        raise ValidationError("Bulk clip-state targets lack unique native identity custody.")
    conn = get_connection(require_project=True, require_timeline=True)
    coordinates = sorted(set((target["trackType"], target["trackIndex"])
                             for target in prepared_input["targets"]))
    rows = []
    protected = []
    expected_set = set(expected_native)
    for track_type, track_index in coordinates:
        items = _call(getattr(conn.timeline, "GetItemListInTrack", None), track_type, track_index) or []
        for item in items:
            native_id = str(_call(getattr(item, "GetUniqueId", None)) or "") or None
            name = str(_call(getattr(item, "GetName", None)) or "")
            start = _call(getattr(item, "GetStart", None))
            end = _call(getattr(item, "GetEnd", None))
            enabled = _call(getattr(item, "GetClipEnabled", None))
            meta = {"timeline_item_id": native_id, "name": name, "track_type": track_type,
                    "track_index": track_index, "start_frame": int(start) if start is not None else None,
                    "end_frame": int(end) if end is not None else None, "enabled": enabled}
            rows.append({"item": item, "meta": meta})
            protected.append({**meta, "enabled": None if native_id in expected_set else enabled})
    protected_digest = _digest(protected)
    by_native: dict[str, dict[str, Any]] = {}
    for row in rows:
        native_id = row["meta"].get("timeline_item_id")
        if native_id not in expected_native:
            continue
        if native_id in by_native:
            raise ValidationError("Bulk clip-state native target became ambiguous.")
        by_native[native_id] = row
    if set(by_native) != set(expected_native):
        raise ValidationError("Bulk clip-state native target disappeared.")
    ordered = []
    for target, native_id in zip(prepared_input["targets"], expected_native):
        row = by_native[native_id]
        meta = row["meta"]
        if ({"track_type": meta.get("track_type"), "track_index": meta.get("track_index"),
             "start_frame": meta.get("start_frame"), "end_frame": meta.get("end_frame"),
             "name": meta.get("name")} !=
            {"track_type": target["trackType"], "track_index": target["trackIndex"],
             "start_frame": target["recordStartFrame"], "end_frame": target["recordEndFrame"],
             "name": target["name"]}):
            raise ValidationError("Bulk clip-state target fields changed before execution.")
        if not isinstance(meta.get("enabled"), bool):
            raise ValidationError("Bulk clip-state enabled readback is unavailable.")
        ordered.append(row)
    return conn, ordered, protected_digest


def _state(context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    _conn, rows, protected_digest = _scan(context, value)
    return {
        "items": [{"timelineItemId": target["id"], "name": target["name"],
                   "enabled": row["meta"]["enabled"]}
                  for target, row in zip(value["targets"], rows)],
        "timelineRevision": value["timelineRevision"],
        "protectedDigest": protected_digest,
    }


def _impact(context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]) -> dict[str, Any]:
    base = context.get("mutationBase")
    if not isinstance(base, Mapping):
        raise ValidationError("Bulk clip-state mutation lacks its carrier mutation base.")
    timeline = context.get("timeline", {})
    targets = [{"kind": "timeline_item", "stableId": target["id"],
                "revision": timeline.get("timelineRevision")} for target in value["targets"]]
    return {**dict(base), "status": "mutation", "effects": [{
        "operation": action_id.removeprefix("cutagent.action."), "kind": "update",
        "trackTypes": sorted(set(target["trackType"] for target in value["targets"])),
        "targets": targets, "placementIntent": "explicit", "broad": False,
        "ambiguous": False, "complete": True,
    }], "closedComposition": True, "complete": True, "ambiguous": False,
        "broad": False, "executableStableTargetPrecondition": True,
        "verificationPolicy": {"minimumEvidence": ["readback", "structural"],
                               "requireProtectedStatePreserved": True,
                               "protectedTargetEvidence": "every_declared_target"}}


@dataclass(frozen=True)
class BulkClipStateDescriptor:
    enabled: bool = True
    operation_class = "mutation"
    version = 1
    capability_id = None

    @property
    def action_id(self) -> str:
        return "cutagent.action.bulk.enable" if self.enabled else "cutagent.action.bulk.disable"

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != {
            "projectId", "timelineId", "timelineRevision", "targets", "failurePolicy"
        } or value.get("failurePolicy") != "stop":
            raise ValidationError("Bulk clip-state input is malformed.")
        targets = value.get("targets")
        if not isinstance(targets, (list, tuple)) or not 1 <= len(targets) <= 1000:
            raise ValidationError("Bulk clip-state requires 1 to 1000 targets.")
        required = {"snapshotId", "id", "trackType", "trackIndex", "recordStartFrame",
                    "recordEndFrame", "name", "mediaPoolItemId", "linkedItemIds"}
        if any(not isinstance(target, Mapping) or set(target) != required for target in targets):
            raise ValidationError("Bulk clip-state target is malformed.")
        ids = [target["id"] for target in targets]
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            raise ValidationError("Bulk clip-state targets must have unique durable identities.")
        return {**dict(value), "targets": [dict(target) for target in targets]}

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        before = _state(context, value)
        timeline_revision = value["timelineRevision"]
        return {"targets": [{"kind": "timeline_item", "stableId": target["id"], "revision": timeline_revision}
                            for target in value["targets"]],
                "preState": before, "impact": _impact(context, self.action_id, value),
                "lowering": {"input": dict(value), "enabled": self.enabled},
                "verification": {"minimumEvidence": ["readback", "structural"]},
                "recovery": {"strategy": "restore_previous_clip_enabled_states"}}

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        value = prepared["lowering"]["input"]
        return {"targets": prepared["targets"], "preState": _state(context, value)}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        value = prepared["lowering"]["input"]
        _conn, rows, _protected_digest = _scan(context, value)
        observations = []
        for target, row in zip(value["targets"], rows):
            item = row["item"]
            before = row["meta"]["enabled"]
            if before != self.enabled and item.SetClipEnabled(self.enabled) is False:
                raise APICallFailed("DaVinci Resolve rejected a bulk clip-state write.")
            after = item.GetClipEnabled()
            if after is not self.enabled:
                raise APICallFailed("Bulk clip-state write failed immediate native readback.")
            observations.append({"timelineItemId": target["id"], "name": target["name"],
                                 "before": before, "after": after, "changed": before != after})
        return {"items": observations, "timelineRevision": value["timelineRevision"]}

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        current = _state(context, prepared["lowering"]["input"])
        passed = (all(item["enabled"] is self.enabled for item in current["items"])
                  and [item["timelineItemId"] for item in current["items"]]
                  == [item["timelineItemId"] for item in result["items"]]
                  and current["protectedDigest"] == prepared["preState"]["protectedDigest"])
        return {"outcome": "passed" if passed else "failed", "evidence": [
            {"modality": "readback", "digest": _digest(current), "summary": "Every exact clip state matched."},
            {"modality": "structural", "digest": _digest(current["timelineRevision"]), "summary": "Timeline binding was preserved."},
        ], "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        try:
            value = prepared["lowering"]["input"]
            _conn, rows, _protected_digest = _scan(context, value)
            before_by_id = {item["timelineItemId"]: item["enabled"] for item in prepared["preState"]["items"]}
            restored = True
            for target, row in zip(value["targets"], rows):
                wanted = before_by_id[target["id"]]
                item = row["item"]
                if item.GetClipEnabled() is not wanted:
                    restored = item.SetClipEnabled(wanted) is not False and restored
                restored = item.GetClipEnabled() is wanted and restored
        except Exception:
            restored = False
        return {"outcome": "succeeded" if restored else "manual_required", "attempted": True,
                "manualActionRequired": not restored}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context, prepared
        return {"actionId": self.action_id, **dict(result)}

    def validate_public_result(self, value: Any) -> bool:
        try:
            return (isinstance(value, Mapping) and set(value) == {"actionId", "items", "timelineRevision"}
                    and value["actionId"] == self.action_id and isinstance(value["timelineRevision"], str)
                    and isinstance(value["items"], (list, tuple)) and len(value["items"]) >= 1
                    and all(isinstance(item, Mapping)
                            and set(item) == {"timelineItemId", "name", "before", "after", "changed"}
                            and isinstance(item["before"], bool) and isinstance(item["after"], bool)
                            and item["after"] is self.enabled
                            and item["changed"] == (item["before"] != item["after"])
                            for item in value["items"]))
        except Exception:
            return False


def bulk_clip_state_prepared_action_descriptors() -> Mapping[str, BulkClipStateDescriptor]:
    descriptors = (BulkClipStateDescriptor(enabled=True), BulkClipStateDescriptor(enabled=False))
    return MappingProxyType({descriptor.action_id: descriptor for descriptor in descriptors})
