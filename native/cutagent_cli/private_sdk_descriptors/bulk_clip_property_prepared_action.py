"""Exact, supported multi-clip Inspector-property prepared action."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from ..connection import get_connection
from ..core import clip_ops
from ..core._clip_ops import properties as property_ops
from ..errors import APICallFailed, ValidationError


_PUBLIC_TO_NATIVE = MappingProxyType({
    "zoomX": "ZoomX", "zoomY": "ZoomY", "positionX": "Pan", "positionY": "Tilt",
    "rotation": "RotationAngle", "anchorX": "AnchorPointX", "anchorY": "AnchorPointY",
    "pitch": "Pitch", "yaw": "Yaw", "flipX": "FlipX", "flipY": "FlipY",
    "opacity": "Opacity", "cropLeft": "CropLeft", "cropRight": "CropRight",
    "cropTop": "CropTop", "cropBottom": "CropBottom", "distortion": "Distortion",
    "dynamicZoomEase": "DynamicZoomEase",
})


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"


def _bindings(context: Mapping[str, Any]) -> tuple[Mapping[str, str], Mapping[str, Any]]:
    private = context.get("privateBindings")
    timeline = context.get("timeline")
    native = private.get("privateTimelineItemNativeIds") if isinstance(private, Mapping) else None
    if not isinstance(native, Mapping) or not isinstance(timeline, Mapping):
        raise ValidationError("Bulk clip-property private target custody is unavailable.")
    return native, timeline


def _call(value: Any, *args: Any) -> Any:
    return value(*args) if callable(value) else None


def _scan(context: Mapping[str, Any], value: Mapping[str, Any]):
    native_by_public, timeline = _bindings(context)
    if (timeline.get("timelineId") != value["timelineId"]
            or timeline.get("timelineRevision") != value["timelineRevision"]):
        raise ValidationError("Bulk clip-property timeline binding is stale.")
    expected_native = [native_by_public.get(row["target"]["id"]) for row in value["items"]]
    if any(not item for item in expected_native) or len(set(expected_native)) != len(expected_native):
        raise ValidationError("Bulk clip-property targets lack unique native identity custody.")
    conn = get_connection(require_project=True, require_timeline=True)
    coordinates = sorted(set((row["target"]["trackType"], row["target"]["trackIndex"])
                             for row in value["items"]))
    inventory = []
    for track_type, track_index in coordinates:
        items = _call(getattr(conn.timeline, "GetItemListInTrack", None), track_type, track_index) or []
        for item in items:
            start = _call(getattr(item, "GetStart", None))
            end = _call(getattr(item, "GetEnd", None))
            inventory.append({"item": item, "meta": {
                "timeline_item_id": str(_call(getattr(item, "GetUniqueId", None)) or "") or None,
                "name": str(_call(getattr(item, "GetName", None)) or ""),
                "track_type": track_type, "track_index": track_index,
                "start_frame": int(start) if start is not None else None,
                "end_frame": int(end) if end is not None else None,
                "clip_color": _call(getattr(item, "GetClipColor", None)),
                "enabled": _call(getattr(item, "GetClipEnabled", None)),
            }})
    by_native = {}
    for row in inventory:
        native_id = row["meta"].get("timeline_item_id")
        if native_id not in expected_native:
            continue
        if native_id in by_native:
            raise ValidationError("Bulk clip-property native target became ambiguous.")
        by_native[native_id] = row
    if set(by_native) != set(expected_native):
        raise ValidationError("Bulk clip-property native target disappeared.")
    ordered = []
    for entry, native_id in zip(value["items"], expected_native):
        target = entry["target"]
        meta = by_native[native_id]["meta"]
        actual = {"track_type": meta.get("track_type"), "track_index": meta.get("track_index"),
                  "start_frame": meta.get("start_frame"), "end_frame": meta.get("end_frame"),
                  "name": meta.get("name")}
        expected = {"track_type": target["trackType"], "track_index": target["trackIndex"],
                    "start_frame": target["recordStartFrame"], "end_frame": target["recordEndFrame"],
                    "name": target["name"]}
        if actual != expected:
            raise ValidationError("Bulk clip-property target fields changed before execution.")
        ordered.append(by_native[native_id])
    protected = [{key: row["meta"].get(key) for key in (
        "timeline_item_id", "track_type", "track_index", "start_frame", "end_frame", "name",
        "clip_color", "enabled",
    )} for row in inventory]
    return conn, ordered, _digest(protected)


def _read(item) -> dict[str, Any]:
    values = {}
    ops = clip_ops._ops_module()
    for public, native in _PUBLIC_TO_NATIVE.items():
        observed = item.GetProperty(native)
        if observed is None:
            raise ValidationError(f"Bulk clip-property readback omitted {public}.")
        values[public] = ops._serialize_dynamic_zoom_ease(observed) if public == "dynamicZoomEase" else observed
    return values


def _native_values(conn, values: Mapping[str, Any]) -> dict[str, Any]:
    kwargs = {
        "zoom_x": values.get("zoomX"), "zoom_y": values.get("zoomY"),
        "position_x": values.get("positionX"), "position_y": values.get("positionY"),
        "rotation": values.get("rotation"), "anchor_x": values.get("anchorX"),
        "anchor_y": values.get("anchorY"), "pitch": values.get("pitch"), "yaw": values.get("yaw"),
        "flip_x": values.get("flipX"), "flip_y": values.get("flipY"), "opacity": values.get("opacity"),
        "crop_left": values.get("cropLeft"), "crop_right": values.get("cropRight"),
        "crop_top": values.get("cropTop"), "crop_bottom": values.get("cropBottom"),
        "distortion": values.get("distortion"), "dynamic_zoom_ease": values.get("dynamicZoomEase"),
    }
    return property_ops._transform_properties(conn, **kwargs, ops_module=clip_ops._ops_module())


def _equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)) \
            and not isinstance(actual, bool) and not isinstance(expected, bool):
        return math.isclose(float(actual), float(expected), abs_tol=1e-6)
    return actual == expected


def _apply_stop(item, values: Mapping[str, Any]) -> list[str]:
    for key, value in values.items():
        if item.SetProperty(key, value) is False:
            return [key]
    return []


def _valid_properties(values: Any) -> bool:
    if not isinstance(values, Mapping) or not values or not set(values).issubset(_PUBLIC_TO_NATIVE):
        return False
    for key, value in values.items():
        if key in {"flipX", "flipY"}:
            if not isinstance(value, bool):
                return False
        elif key == "dynamicZoomEase":
            if value not in {"linear", "in", "out", "inout"}:
                return False
        elif (not isinstance(value, (int, float)) or isinstance(value, bool)
              or not math.isfinite(float(value))):
            return False
        elif key == "opacity" and not 0 <= float(value) <= 100:
            return False
    return True


def _state(context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
    _conn, rows, protected = _scan(context, value)
    return {"items": [{"clipId": entry["target"]["id"], "properties": _read(row["item"])}
                      for entry, row in zip(value["items"], rows)],
            "timelineRevision": value["timelineRevision"], "protectedDigest": protected}


@dataclass(frozen=True)
class BulkClipPropertyDescriptor:
    action_id = "cutagent.action.bulk.property_set"
    operation_class = "mutation"
    version = 1
    capability_id = None

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != {
            "projectId", "timelineId", "timelineRevision", "items", "failurePolicy"
        } or value.get("failurePolicy") != "stop":
            raise ValidationError("Bulk clip-property input is malformed.")
        items = value.get("items")
        if not isinstance(items, (list, tuple)) or not 1 <= len(items) <= 1000:
            raise ValidationError("Bulk clip-property input requires 1 to 1000 items.")
        target_keys = {"snapshotId", "id", "trackType", "trackIndex", "recordStartFrame",
                       "recordEndFrame", "name", "mediaPoolItemId", "linkedItemIds"}
        ids = []
        for row in items:
            if not isinstance(row, Mapping) or set(row) != {"target", "properties"}:
                raise ValidationError("Bulk clip-property item is malformed.")
            target, properties = row["target"], row["properties"]
            if not isinstance(target, Mapping) or set(target) != target_keys or target.get("trackType") != "video":
                raise ValidationError("Bulk clip-property target is malformed.")
            if not _valid_properties(properties):
                raise ValidationError("Bulk clip-property values contain no supported property set.")
            ids.append(target.get("id"))
        if any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids):
            raise ValidationError("Bulk clip-property targets require unique durable identities.")
        return {**dict(value), "items": [{"target": dict(row["target"]),
                                          "properties": dict(row["properties"])} for row in items]}

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        before = _state(context, value)
        targets = [{"kind": "clip", "stableId": row["target"]["id"],
                    "revision": value["timelineRevision"]} for row in value["items"]]
        base = context.get("mutationBase")
        if not isinstance(base, Mapping):
            raise ValidationError("Bulk clip-property mutation lacks its carrier mutation base.")
        impact = {**dict(base), "status": "mutation", "effects": [{
            "operation": "bulk.property_set", "kind": "update", "trackTypes": ["video"],
            "targets": targets, "placementIntent": "explicit", "broad": False,
            "ambiguous": False, "complete": True,
        }], "closedComposition": True, "complete": True, "ambiguous": False,
            "broad": False, "executableStableTargetPrecondition": True,
            "verificationPolicy": {"minimumEvidence": ["readback", "structural"],
                                   "requireProtectedStatePreserved": True,
                                   "protectedTargetEvidence": "every_declared_target"}}
        return {"targets": targets, "preState": before, "impact": impact,
                "lowering": {"input": dict(value)},
                "verification": {"minimumEvidence": ["readback", "structural"]},
                "recovery": {"strategy": "restore_previous_clip_properties"}}

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        return {"targets": prepared["targets"], "preState": _state(context, prepared["lowering"]["input"])}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        value = prepared["lowering"]["input"]
        conn, rows, _protected = _scan(context, value)
        observations = []
        for entry, row in zip(value["items"], rows):
            before = _read(row["item"])
            failed = _apply_stop(row["item"], _native_values(conn, entry["properties"]))
            if failed:
                raise APICallFailed("DaVinci Resolve rejected a supported bulk clip-property write.",
                                    details={"failed_properties": failed})
            after = _read(row["item"])
            if any(not _equal(after[key], wanted) for key, wanted in entry["properties"].items()):
                raise APICallFailed("Bulk clip-property write failed immediate native readback.")
            observations.append({"clipId": entry["target"]["id"], "before": before, "after": after,
                                 "changed": _digest(before) != _digest(after)})
        return {"items": observations, "timelineRevision": value["timelineRevision"],
                "protectedStatePreserved": True, "stoppedAfterFailure": False}

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        value = prepared["lowering"]["input"]
        current = _state(context, value)
        expected_ids = [row["target"]["id"] for row in value["items"]]
        passed = (current["protectedDigest"] == prepared["preState"]["protectedDigest"]
                  and [row["clipId"] for row in current["items"]] == expected_ids
                  and all(all(_equal(current["items"][index]["properties"][key], wanted)
                                  for key, wanted in entry["properties"].items())
                          for index, entry in enumerate(value["items"])))
        return {"outcome": "passed" if passed else "failed", "evidence": [
            {"modality": "readback", "digest": _digest(current["items"]),
             "summary": "Every exact clip property matched independent readback."},
            {"modality": "structural", "digest": current["protectedDigest"],
             "summary": "Unrelated timeline-item structure was preserved."},
        ], "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        try:
            value = prepared["lowering"]["input"]
            conn, rows, _protected = _scan(context, value)
            before = {row["clipId"]: row["properties"] for row in prepared["preState"]["items"]}
            restored = True
            for entry, row in zip(value["items"], rows):
                property_ops._apply_transform_properties(
                    row["item"], _native_values(conn, before[entry["target"]["id"]]),
                )
                readback_matches = (
                    _digest(_read(row["item"]))
                    == _digest(before[entry["target"]["id"]])
                )
                restored = readback_matches and restored
        except Exception:
            restored = False
        return {"outcome": "succeeded" if restored else "manual_required", "attempted": True,
                "manualActionRequired": not restored}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context, prepared
        return {"actionId": self.action_id, **dict(result)}

    def validate_public_result(self, value: Any) -> bool:
        return (isinstance(value, Mapping)
                and set(value) == {"actionId", "items", "timelineRevision", "protectedStatePreserved", "stoppedAfterFailure"}
                and value.get("actionId") == self.action_id and value.get("protectedStatePreserved") is True
                and value.get("stoppedAfterFailure") is False and isinstance(value.get("timelineRevision"), str)
                and isinstance(value.get("items"), (list, tuple)) and len(value["items"]) >= 1
                and all(isinstance(row, Mapping)
                        and set(row) == {"clipId", "before", "after", "changed"}
                        and row["changed"] == (_digest(row["before"]) != _digest(row["after"]))
                        for row in value["items"]))


def bulk_clip_property_prepared_action_descriptors() -> Mapping[str, BulkClipPropertyDescriptor]:
    descriptor = BulkClipPropertyDescriptor()
    return MappingProxyType({descriptor.action_id: descriptor})
