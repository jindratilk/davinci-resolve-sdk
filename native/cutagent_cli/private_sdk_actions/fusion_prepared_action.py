"""Eight-stage prepared-action contribution for Fusion, DCTL, and LUT.

The public SDK sees only closed action inputs and normalized results. This
module owns exact target binding, complete Mutation Policy impact, private
lowering, independent verification, checkpoint recovery, and public projection.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import base64
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping

from .errors import FusionDescriptorValidationError as InventoryValidationError
from .fusion_evidence import fusion_minimum_evidence
from .packaged_action_contracts import (
    reviewed_action_input_schema,
    reviewed_action_result_schema,
)


class _LazyFusionPreparedActionRuntime:
    """Avoid loading DaVinci Resolve/auth dependencies during inventory imports."""

    def __init__(self) -> None:
        self._instance: Any | None = None

    def _runtime(self) -> Any:
        if self._instance is None:
            from .fusion_runtime import FusionPreparedActionRuntime

            self._instance = FusionPreparedActionRuntime()
        return self._instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runtime(), name)


DELEGATED_ACTIONS = MappingProxyType({
    "cutagent.action.fusion.apply": "delegated_to_reviewed_fusion_graph_runtime",
})
UNAVAILABLE_ACTIONS = MappingProxyType({
    "cutagent.action.fusion.comp.play": "fusion_api_exposes_no_authoritative_playback_state_or_recovery",
    "cutagent.action.fusion.comp.stop": "fusion_api_exposes_no_authoritative_playback_state_or_recovery",
    "cutagent.action.fusion.tool.copy": "process_clipboard_has_no_receipt_bound_identity_or_readback",
    "cutagent.action.fusion.tool.paste": "process_clipboard_has_no_receipt_bound_identity_or_readback",
    "cutagent.action.fusion.macro.apply": "macro_name_can_resolve_unbound_filesystem_content",
    "cutagent.action.fusion.comp.render": "render_handler_has_no_authoritative_completion_evidence",
})

_ALL_COMMAND_IDS = frozenset({
    "fusion.apply", "fusion.comp.current", "fusion.comp.delete", "fusion.comp.play", "fusion.comp.range",
    "fusion.comp.rename", "fusion.comp.render", "fusion.comp.stop",
    "fusion.effect.blur", "fusion.effect.color_correct", "fusion.effect.glow",
    "fusion.effect.sharpen", "fusion.effect.transform", "fusion.generate",
    "fusion.image.batch", "fusion.image.set", "fusion.insert_setting", "fusion.insert_settings.batch", "fusion.keyer.chroma",
    "fusion.keyframe.add", "fusion.keyframe.clear", "fusion.keyframe.delete", "fusion.keyframe.list",
    "fusion.keyframe.set", "fusion.macro.apply", "fusion.mask.ellipse",
    "fusion.mask.polygon", "fusion.mask.rectangle", "fusion.nested_text.batch", "fusion.nested_text.update",
    "fusion.node.add", "fusion.node.connect", "fusion.node.delete",
    "fusion.node.disconnect", "fusion.setting.center_to_polypath",
    "fusion.setting.polypath_to_center", "fusion.setting.validate",
    "fusion.template.apply", "fusion.template.assets.add", "fusion.template.dir", "fusion.template.show",
    "fusion.template.icon.set", "fusion.template.install",
    "fusion.template.package_drfx", "fusion.template.scaffold",
    "fusion.template.uninstall", "fusion.text.batch", "fusion.text.set", "fusion.tool.active",
    "fusion.tool.add", "fusion.tool.attrs", "fusion.tool.connect", "fusion.tool.copy", "fusion.tool.get", "fusion.tool.inputs", "fusion.tool.list", "fusion.tool.registry", "fusion.tool.outputs",
    "fusion.tool.delete", "fusion.tool.disconnect", "fusion.tool.paste",
    "fusion.tool.set", "fusion.tracker.add", "dctl.apply", "lut_refresh",
    "fusion.setting.inspect", "fusion.setting.summary",
    "fusion.template.assets.list", "fusion.template.validate",
    "lut.convert", "lut.generate.identity", "lut.inspect", "lut.install", "lut.list", "lut.remove", "lut.validate",
})
_READ_COMMANDS = frozenset({
    "fusion.comp.current", "fusion.keyframe.list", "fusion.setting.inspect", "fusion.setting.summary",
    "fusion.setting.center_to_polypath", "fusion.setting.polypath_to_center",
    "fusion.template.assets.list", "fusion.template.show", "fusion.template.validate",
    "fusion.tool.attrs", "fusion.tool.get", "fusion.tool.inputs", "fusion.tool.list", "fusion.tool.registry", "fusion.tool.outputs",
    "lut.convert", "lut.inspect", "lut.list", "lut.validate",
})
_FILESYSTEM_COMMANDS = frozenset({
    "fusion.generate", "fusion.template.assets.add", "fusion.template.dir",
    "fusion.template.icon.set", "fusion.template.install",
    "fusion.template.package_drfx", "fusion.template.scaffold",
    "fusion.template.uninstall", "lut.generate.identity", "lut.install", "lut.remove",
})
_ARTIFACT_FIELDS = frozenset({
    "artifactId", "assetArtifactId", "dctlArtifactId",
    "directoryArtifactId",
    "imageArtifactId", "pngArtifactId",
    "installedArtifactId", "settingArtifactId", "sourceArtifactId", "templateArtifactId",
})


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"


def _revision(value: Any) -> str:
    return f"revision_{hashlib.sha256(_canonical(value)).hexdigest()}"


def _public_timeline_item_id(timeline_id: str, native_id: str) -> str:
    payload = _canonical({"nativeId": native_id, "timelineId": timeline_id})
    return "timeline_item_f" + base64.urlsafe_b64encode(
        hashlib.sha256(payload).digest()
    ).decode("ascii").rstrip("=")


@lru_cache(maxsize=None)
def _capability_id(command_id: str) -> str:
    from ..command_catalog import get_command_catalog

    capability_id = next(
        (row.capability_id for row in get_command_catalog() if row.command_id == command_id),
        None,
    )
    if not isinstance(capability_id, str) or not capability_id:
        raise InventoryValidationError(f"Fusion action has no authoritative capability binding: {command_id}")
    return capability_id


def _validate(value: Any, schema: Mapping[str, Any], path: str) -> None:
    if "oneOf" in schema:
        matches = 0
        for branch in schema["oneOf"]:
            try:
                _validate(value, branch, path)
            except InventoryValidationError:
                continue
            matches += 1
        if matches != 1:
            raise InventoryValidationError(f"Fusion action value does not match exactly one schema at {path}")
        return
    if "const" in schema and value != schema["const"]:
        raise InventoryValidationError(f"Fusion action value violates const at {path}")
    if "enum" in schema and value not in schema["enum"]:
        raise InventoryValidationError(f"Fusion action value violates enum at {path}")
    expected = schema.get("type")
    types = set(expected if isinstance(expected, list) else [expected]) if expected else set()
    valid_type = (
        ("null" in types and value is None)
        or ("boolean" in types and isinstance(value, bool))
        or ("integer" in types and isinstance(value, int) and not isinstance(value, bool))
        or ("number" in types and isinstance(value, (int, float)) and not isinstance(value, bool))
        or ("string" in types and isinstance(value, str))
        or ("array" in types and isinstance(value, list))
        or ("object" in types and isinstance(value, Mapping))
        or not types
    )
    if not valid_type:
        raise InventoryValidationError(f"Fusion action value has invalid type at {path}")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)) or len(value) > int(schema.get("maxLength", 2**31)):
            raise InventoryValidationError(f"Fusion action string length is invalid at {path}")
        if schema.get("pattern") and re.fullmatch(str(schema["pattern"]), value) is None:
            raise InventoryValidationError(f"Fusion action identifier is invalid at {path}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise InventoryValidationError(f"Fusion action number must be finite at {path}")
        if "minimum" in schema and value < schema["minimum"]:
            raise InventoryValidationError(f"Fusion action number is below minimum at {path}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise InventoryValidationError(f"Fusion action number is below exclusive minimum at {path}")
        if "maximum" in schema and value > schema["maximum"]:
            raise InventoryValidationError(f"Fusion action number exceeds maximum at {path}")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)) or len(value) > int(schema.get("maxItems", 2**31)):
            raise InventoryValidationError(f"Fusion action array length is invalid at {path}")
        for index, item in enumerate(value):
            _validate(item, schema.get("items", {}), f"{path}[{index}]")
    if isinstance(value, Mapping):
        required = set(schema.get("required", ()))
        if not required <= set(value):
            raise InventoryValidationError(f"Fusion action object is missing required fields at {path}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise InventoryValidationError(f"Fusion action object contains unreviewed fields at {path}")
        for key, child in value.items():
            if key in properties:
                _validate(child, properties[key], f"{path}.{key}")


def _schemas(action_id: str, command_id: str) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    expected_action_id = f"cutagent.action.{command_id}"
    if action_id != expected_action_id:
        raise InventoryValidationError(f"Fusion packet action identity mismatch: {action_id}")
    input_schema = reviewed_action_input_schema(action_id)
    result_schema = reviewed_action_result_schema(action_id)
    if not isinstance(input_schema, Mapping) or not isinstance(result_schema, Mapping):
        raise InventoryValidationError(f"Fusion packet has no closed contract for {action_id}")
    return input_schema, result_schema


def _artifact_fields(value: Any):
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _ARTIFACT_FIELDS and isinstance(child, str):
                yield key, child
            else:
                yield from _artifact_fields(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _artifact_fields(child)


def _artifact_digests(context: Mapping[str, Any], value: Mapping[str, Any], runtime: Any) -> list[str]:
    records = context.get("privateManagedArtifacts")
    result = []
    for key, artifact_id in _artifact_fields(value):
        record = records.get(artifact_id) if isinstance(records, Mapping) else None
        if not isinstance(record, Mapping):
            record = runtime.managed_artifact_record(context, artifact_id)
        digest = None
        if isinstance(record, Mapping):
            digest = record.get("treeDigest") if key == "directoryArtifactId" else record.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", digest) is None:
            raise InventoryValidationError(f"managed input artifact digest is unavailable for {key}")
        result.append(digest if digest.startswith("sha256:") else f"sha256:{digest}")
    return sorted(set(result))


def _operation_kind(command_id: str) -> str:
    if any(token in command_id for token in (".delete", ".uninstall", ".disconnect", ".clear", ".remove")):
        return "delete"
    if any(token in command_id for token in (".add", ".insert", ".generate", ".install", ".scaffold")):
        return "create"
    return "update"


def _mutation_targets(
    context: Mapping[str, Any], targets: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Project private target aliases onto the public Mutation Policy taxonomy."""
    binding = context.get("exactRequestBinding")
    identities = binding.get("identities") if isinstance(binding, Mapping) else None
    target_ids = identities.get("targetIds") if isinstance(identities, Mapping) else None
    exact_target_ids = set(target_ids) if isinstance(target_ids, (list, tuple)) else set()
    project_library_id = identities.get("projectLibraryId") if isinstance(identities, Mapping) else None
    project_id = identities.get("projectId") if isinstance(identities, Mapping) else None
    timeline_id = identities.get("timelineId") if isinstance(identities, Mapping) else None
    private_context = context.get("privateBindings")
    if not isinstance(private_context, Mapping):
        private_context = context
    private_bindings = private_context.get("privateTargetBindings")
    managed_artifacts = private_context.get("privateManagedArtifacts")
    allowed_kinds = {
        "project_library", "project", "timeline", "track", "clip",
        "fusion_composition", "media", "marker", "runtime_setting",
    }
    projected = []
    for target in targets:
        stable_id = target.get("stableId")
        revision = target.get("revision")
        if not isinstance(stable_id, str) or not isinstance(revision, str):
            raise InventoryValidationError("Fusion mutation target identity is incomplete")
        kind = target.get("kind")
        if kind not in allowed_kinds:
            native_binding = (
                private_bindings.get(stable_id)
                if isinstance(private_bindings, Mapping)
                else None
            )
            if stable_id == project_library_id:
                kind = "project_library"
            elif stable_id == project_id:
                kind = "project"
            elif stable_id == timeline_id:
                kind = "timeline"
            elif isinstance(native_binding, Mapping) and native_binding.get("kind") == "timeline_item":
                kind = "clip"
            elif stable_id in exact_target_ids and re.fullmatch(
                r".+:fusion:[1-9][0-9]*", stable_id
            ):
                kind = "fusion_composition"
            elif isinstance(managed_artifacts, Mapping) and stable_id in managed_artifacts:
                kind = "media"
            elif stable_id in exact_target_ids and re.fullmatch(
                r"coordinate_[a-f0-9]{64}|private_target_[a-f0-9]{32}", stable_id
            ):
                kind = "runtime_setting"
            else:
                raise InventoryValidationError(
                    "Fusion mutation target has no authoritative public taxonomy binding"
                )
        projected.append({"kind": kind, "stableId": stable_id, "revision": revision})
    return projected


def _tool_result(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, str]:
    before_nodes = {row["name"]: row for row in before.get("graph", {}).get("nodes", [])}
    after_nodes = {row["name"]: row for row in after.get("graph", {}).get("nodes", [])}
    names = sorted(set(after_nodes) - set(before_nodes))
    if len(names) != 1:
        raise InventoryValidationError("Fusion action did not create exactly one tool")
    row = after_nodes[names[0]]
    return {"name": names[0], "type": str(row.get("type") or "Unknown")}


def _node_map(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    graph = state.get("graph") if isinstance(state, Mapping) else None
    nodes = graph.get("nodes") if isinstance(graph, Mapping) else None
    return {
        str(row["name"]): row
        for row in nodes or []
        if isinstance(row, Mapping) and isinstance(row.get("name"), str)
    }


def _point(value: Mapping[str, Any], key: str, default: tuple[float, float]) -> dict[str, float]:
    candidate = value.get(key)
    return (
        {"x": float(candidate["x"]), "y": float(candidate["y"])}
        if isinstance(candidate, Mapping)
        else {"x": default[0], "y": default[1]}
    )


def _source_position(value: Mapping[str, Any]) -> dict[str, Any]:
    return deepcopy(dict(value.get("sourcePosition") or {"domain": "source", "value": {"kind": "frames", "value": 0}}))


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > 65536:
            raise InventoryValidationError("Fusion observed text exceeds the public value bound")
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping) and set(value) == {"x", "y"}:
        return {"x": float(value["x"]), "y": float(value["y"])}
    if isinstance(value, list) and len(value) <= 16 and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
        return deepcopy(value)
    return str(value)


def _public_projection(command_id: str, value: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    action_id = f"cutagent.action.{command_id}"
    before = result["before"]
    after = result["after"]
    native_value = result.get("nativeResult")
    native = native_value if isinstance(native_value, Mapping) else {}
    if command_id == "fusion.image.batch":
        rows = []
        before_items = before.get("items") if isinstance(before.get("items"), list) else []
        after_items = after.get("items") if isinstance(after.get("items"), list) else []
        native_rows = native.get("results") if isinstance(native.get("results"), list) else []
        for index, item in enumerate(value["items"]):
            native_row = native_rows[index] if index < len(native_rows) and isinstance(native_rows[index], Mapping) else {}
            common = {
                "index": index,
                "timelineItemId": item["timelineItemId"],
                "compositionIndex": int(item["compositionIndex"]),
                "imageArtifactId": item["imageArtifactId"],
                "durationMs": float(native_row.get("durationMs") or 0),
            }
            if native_row.get("ok") is True:
                observed = native_row.get("result") if isinstance(native_row.get("result"), Mapping) else {}
                verification = observed.get("verification") if isinstance(observed.get("verification"), Mapping) else {}
                group = verification.get("group_input") if isinstance(verification.get("group_input"), Mapping) else {}
                loaders = verification.get("loaders") if isinstance(verification.get("loaders"), list) else []
                loader = loaders[0] if loaders and isinstance(loaders[0], Mapping) else {}
                rows.append({
                    **common, "ok": True,
                    "toolName": str(group.get("tool") or loader.get("tool") or item.get("groupToolName") or "Loader1"),
                    "inputName": str(group.get("input") or item.get("groupInputName") or "Clip"),
                    "verified": True,
                    "revisionBefore": _revision(before_items[index]),
                    "revisionAfter": _revision(after_items[index]),
                })
            else:
                error = native_row.get("error") if isinstance(native_row.get("error"), Mapping) else {}
                rows.append({**common, "ok": False, "error": {
                    "code": str(error.get("code") or "fusion_image_replacement_failed"),
                    "message": str(error.get("message") or "Fusion image replacement failed."),
                }})
        return {
            "actionId": action_id,
            "results": rows,
            "successCount": sum(row["ok"] is True for row in rows),
            "failureCount": sum(row["ok"] is False for row in rows),
            "durationMs": float(native.get("durationMs") or 0),
            "protectedStatePreserved": True,
        }
    overwritten = any(
        isinstance(state, Mapping) and state.get("kind") != "absent"
        for key, state in before.items() if str(key).startswith("affected_")
    )

    def output_artifact() -> tuple[int, str]:
        file_states = [
            state for state in after.values()
            if isinstance(state, Mapping) and state.get("kind") == "file"
        ]
        if len(file_states) != 1:
            raise InventoryValidationError("output action did not produce exactly one verified file")
        byte_count = file_states[0].get("size")
        digest = file_states[0].get("sha256")
        if (
            not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count < 1
            or not isinstance(digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", digest) is None
        ):
            raise InventoryValidationError("output action has no exact verified file digest")
        return byte_count, digest

    def copied_overwrite_truth() -> bool:
        native_value = native.get("overwritten")
        if not isinstance(native_value, bool) or native_value != overwritten:
            raise InventoryValidationError("copy result overwrite truth disagrees with exact pre-state")
        return native_value
    revision_after = _revision(after)
    revision = {
        "revisionBefore": str(value.get("revision") or _revision(before)),
        "revisionAfter": revision_after,
        "changed": before != after,
    }
    if command_id == "fusion.nested_text.batch":
        native_rows = native.get("results")
        before_items = before.get("items")
        after_items = after.get("items")
        updates = value.get("updates")
        if not all(isinstance(rows, list) for rows in (native_rows, before_items, after_items, updates)):
            raise InventoryValidationError("Nested Fusion text batch result is incomplete")
        if not (len(native_rows) == len(before_items) == len(after_items) == len(updates)):
            raise InventoryValidationError("Nested Fusion text batch result cardinality drifted")
        rows = []
        for index, (update, native_row, before_item, after_item) in enumerate(
            zip(updates, native_rows, before_items, after_items)
        ):
            if native_row.get("ok"):
                rows.append({
                    "index": index,
                    "status": "succeeded",
                    "timelineItemId": update["timelineItemId"],
                    "headerUpdated": bool(native_row.get("header_updated")),
                    "bodyUpdated": bool(native_row.get("body_updated")),
                    "revisionBefore": _revision(before_item),
                    "revisionAfter": _revision(after_item),
                })
            else:
                error = native_row.get("error") if isinstance(native_row.get("error"), Mapping) else {}
                rows.append({
                    "index": index,
                    "status": "failed",
                    "timelineItemId": update["timelineItemId"],
                    "code": str(error.get("code") or "API_CALL_FAILED")[:128],
                    "message": str(error.get("message") or "Nested Fusion text update failed")[:4096],
                })
        return {
            "actionId": action_id,
            "projectId": value["projectId"],
            "timelineId": value["timelineId"],
            "revisionBefore": value["revision"],
            "revisionAfter": revision_after,
            "changed": any(
                row["status"] == "succeeded" and (row["headerUpdated"] or row["bodyUpdated"])
                for row in rows
            ),
            "successCount": sum(row["status"] == "succeeded" for row in rows),
            "failureCount": sum(row["status"] == "failed" for row in rows),
            "results": rows,
            "protectedStatePreserved": True,
        }
    tool = _tool_result(before, after) if command_id in {
        "fusion.effect.blur", "fusion.effect.color_correct", "fusion.effect.glow",
        "fusion.effect.sharpen", "fusion.effect.transform", "fusion.keyer.chroma",
        "fusion.mask.ellipse", "fusion.mask.polygon", "fusion.mask.rectangle",
        "fusion.node.add", "fusion.tool.add", "fusion.tracker.add",
    } else None
    if command_id == "fusion.comp.delete":
        body = {"timelineItemId": value["timelineItemId"], "compositionIndex": value["compositionIndex"], "deleted": True, "revision": revision}
        field = "deletion"
    elif command_id == "fusion.comp.rename":
        body = {"timelineItemId": value["timelineItemId"], "compositionIndex": value["compositionIndex"], "previousName": native["previousName"], "currentName": value["newName"], "revision": revision}
        field = "rename"
    elif command_id == "fusion.comp.range":
        body, field = {"range": deepcopy(value["range"]), "revision": revision}, "compositionRange"
    elif command_id == "fusion.comp.render":
        body, field = {"started": True, "completed": True, "revision": revision}, "render"
    elif command_id == "fusion.comp.current":
        body, field = {
            "name": str(after.get("name") or "Composition"),
            "sourceStart": {"domain": "source", "value": {"kind": "frames", "value": int(after.get("renderStart") or 0)}},
            "sourceEnd": {"domain": "source", "value": {"kind": "frames", "value": int(after.get("renderEnd") or 0)}},
        }, "composition"
    elif command_id.startswith("fusion.effect."):
        fields = {
            "fusion.effect.blur": {"blurStrength": float(value.get("blurStrength", 5.0))},
            "fusion.effect.color_correct": {"redGain": float(value.get("redGain", 1)), "greenGain": float(value.get("greenGain", 1)), "blueGain": float(value.get("blueGain", 1)), "gamma": float(value.get("gamma", 1)), "saturation": float(value.get("saturation", 1))},
            "fusion.effect.glow": {"intensity": float(value.get("intensity", .5))},
            "fusion.effect.sharpen": {"amount": float(value.get("amount", .5))},
            "fusion.effect.transform": {"zoom": float(value.get("zoom", 1)), "position": _point(value, "position", (0, 0)), "rotationDegrees": float(value.get("rotationDegrees", 0))},
        }[command_id]
        body, field = {"tool": tool, **fields, "revision": revision}, "effect"
    elif command_id == "fusion.keyer.chroma":
        body, field = {"tool": tool, "keyColor": value.get("keyColor", "green"), "threshold": float(value.get("threshold", .3)), "revision": revision}, "keyer"
    elif command_id in {"fusion.keyframe.add", "fusion.keyframe.set"}:
        body, field = {"toolName": value["toolName"], "inputName": value["inputName"], "sourcePosition": _source_position(value), "value": deepcopy(value["value"]), "revision": revision}, "keyframe"
    elif command_id == "fusion.keyframe.delete":
        body, field = {"toolName": value["toolName"], "inputName": value["inputName"], "sourcePosition": _source_position(value), "deleted": True, "revision": revision}, "keyframe"
    elif command_id == "fusion.keyframe.clear":
        before_row = next((row for node in before.get("graph", {}).get("nodes", []) if node.get("name") == value["toolName"] for row in node.get("inputs", []) if row.get("id") == value["inputName"]), {})
        body, field = {"toolName": value["toolName"], "inputName": value["inputName"], "removedCount": len(before_row.get("keyframes") or {}), "revision": revision}, "keyframes"
    elif command_id == "fusion.keyframe.list":
        rows = native_value if isinstance(native_value, list) else native.get("keyframes", [])
        body, field = [{"sourcePosition": {"domain": "source", "value": {"kind": "frames", "value": int(row.get("frame", 0))}}, "value": _safe_value(row.get("value"))} for row in rows if isinstance(row, Mapping)], "keyframes"
    elif command_id in {"fusion.mask.ellipse", "fusion.mask.rectangle"}:
        body, field = {"tool": tool, "center": _point(value, "center", (.5, .5)), "width": float(value.get("width", .5)), "height": float(value.get("height", .5)), "softness": float(value.get("softness", 0)), "revision": revision}, "mask"
    elif command_id == "fusion.mask.polygon":
        body, field = {"tool": tool, "points": deepcopy(value["points"]), "revision": revision}, "mask"
    elif command_id in {"fusion.node.add", "fusion.tool.add"}:
        added_name = tool["name"] if isinstance(tool, Mapping) else ""
        added_node = _node_map(after).get(added_name, {})
        position = added_node.get("flowPosition")
        if not isinstance(position, Mapping) and value.get("flowPosition") is not None:
            raise InventoryValidationError("Fusion tool flow position was not independently read back")
        body, field = {"tool": tool, "flowPosition": deepcopy(dict(position)) if isinstance(position, Mapping) else None, "revision": revision}, "node" if command_id == "fusion.node.add" else "tool"
    elif command_id in {"fusion.node.connect", "fusion.tool.connect"}:
        body, field = {"source": deepcopy(value["source"]), "destination": deepcopy(value["destination"]), "connected": True, "revision": revision}, "connection"
    elif command_id in {"fusion.node.delete", "fusion.tool.delete"}:
        body, field = {"toolName": value["toolName"], "deleted": True, "revision": revision}, "node" if command_id == "fusion.node.delete" else "tool"
    elif command_id in {"fusion.node.disconnect", "fusion.tool.disconnect"}:
        body, field = {"destination": deepcopy(value["destination"]), "disconnected": True, "revision": revision}, "connection"
    elif command_id == "fusion.tool.active":
        body, field = {"tool": {"name": value["toolName"], "type": str(next(row.get("type") for row in after["graph"]["nodes"] if row.get("name") == value["toolName"]))}, "changed": before.get("activeTool") != after.get("activeTool"), "revision": revision}, "activeTool"
    elif command_id == "fusion.tool.set":
        body, field = {
            "timelineItemId": value["timelineItemId"],
            "compositionIndex": int(value["compositionIndex"]),
            "toolName": value["toolName"],
            "inputName": value["inputName"],
            "sourcePosition": _source_position(value),
            "value": deepcopy(value["value"]),
            "revision": revision,
        }, "toolValue"
    elif command_id == "fusion.tracker.add":
        body, field = {"tool": tool, "patternCenter": _point(value, "patternCenter", (.5, .5)), "revision": revision}, "tracker"
    elif command_id == "fusion.tool.paste":
        before_nodes = _node_map(before)
        after_nodes = _node_map(after)
        pasted = [
            {"name": name, "type": str(after_nodes[name].get("type") or "Unknown")}
            for name in sorted(set(after_nodes) - set(before_nodes))
        ]
        body, field = {"pastedTools": pasted, "pastedCount": len(pasted), "revision": revision}, "clipboard"
    elif command_id == "fusion.tool.list":
        rows = native_value if isinstance(native_value, list) else []
        body, field = [{"name": str(row.get("name") or row.get("id") or "Tool"), "type": str(row.get("type") or "Unknown")} for row in rows if isinstance(row, Mapping)], "tools"
    elif command_id == "fusion.tool.attrs":
        body, field = [{"name": str(key), "value": _safe_value(value_)} for key, value_ in native.items()], "attributes"
    elif command_id == "fusion.tool.get":
        input_name = str(value.get("inputName") or next(iter(native), "value"))
        body, field = {"timelineItemId": value["timelineItemId"], "compositionIndex": int(value["compositionIndex"]), "toolName": value["toolName"], "inputName": input_name, "sourcePosition": _source_position(value), "value": _safe_value(native.get(input_name))}, "toolValue"
    elif command_id in {"fusion.tool.inputs", "fusion.tool.outputs"}:
        rows = native_value if isinstance(native_value, list) else []
        body = (
            [{"name": str(row.get("name") or row.get("id") or "Input"), "id": str(row.get("id") or row.get("name") or "Input"), "value": _safe_value(row.get("value"))} for row in rows if isinstance(row, Mapping)]
            if command_id.endswith("inputs")
            else [{"name": str(row.get("name") or row.get("id") or "Output"), "id": str(row.get("id") or row.get("name") or "Output")} for row in rows if isinstance(row, Mapping)]
        )
        field = "inputs" if command_id.endswith("inputs") else "outputs"
    elif command_id in {"fusion.setting.center_to_polypath", "fusion.setting.polypath_to_center"}:
        body, field = deepcopy(dict(native)), "coordinate"
    elif command_id == "dctl.apply":
        body, field = {"projectId": value["projectId"], "timelineId": value["timelineId"], "revisionBefore": value["revision"], "revisionAfter": revision_after, "timelineItemId": value["timelineItemId"], "nodeIndex": int(value.get("nodeIndex", 1)), "dctlArtifactId": value["dctlArtifactId"], "readbackName": native["readbackName"], "applied": True}, "application"
    elif command_id == "lut_refresh":
        body, field = {"projectId": value["projectId"], "revisionBefore": value["revision"], "revisionAfter": revision_after, "changed": True, "verificationStatus": "pending_manual", "apiAcknowledged": True}, "refresh"
    elif command_id in {"fusion.insert_setting", "fusion.insert_settings.batch"}:
        requested = [value] if command_id == "fusion.insert_setting" else list(value["items"])
        remaining = [row for row in after.get("items", []) if row.get("nativeId") not in {item.get("nativeId") for item in before.get("items", [])}]
        inserted = []
        for item in requested:
            requested_track = item.get("videoTrackIndex")
            matches = [row for row in remaining if (
                row.get("start") == int(item["recordPosition"]["value"]["value"])
                and row.get("duration") == int(item["clipDuration"]["value"]["value"])
                and (requested_track is None or row.get("track") == int(requested_track))
                and (item.get("clipName") is None or row.get("name") == item.get("clipName"))
            )]
            if len(matches) != 1:
                raise InventoryValidationError("Fusion setting insertion did not create one exact timeline item per request")
            row = matches[0]
            remaining.remove(row)
            record_position = deepcopy(item["recordPosition"])
            record_position["value"]["value"] = row["start"]
            clip_duration = deepcopy(item["clipDuration"])
            clip_duration["value"]["value"] = row["duration"]
            inserted.append({
                "timelineItemId": _public_timeline_item_id(str(value["timelineId"]), str(row["nativeId"])),
                "clipName": row["name"],
                "recordPosition": record_position,
                "clipDuration": clip_duration,
                "videoTrackIndex": row["track"],
            })
        if command_id == "fusion.insert_setting":
            body, field = {**inserted[0], "revision": revision}, "insertedItem"
        else:
            body, field = {"items": inserted, "revision": revision}, "insertedItems"
    elif command_id == "fusion.text.batch":
        native_rows = native.get("results") if isinstance(native, Mapping) else None
        if not isinstance(native_rows, list) or len(native_rows) != len(value["updates"]):
            raise InventoryValidationError("Fusion text batch result lost item correlation")
        body, field = {
            "updates": [
                {
                    "timelineItemId": update["timelineItemId"],
                    "compositionIndex": int(update["compositionIndex"]),
                    "toolName": update["toolName"],
                    "inputName": update["inputName"],
                    "text": update["text"],
                    "verified": bool(native_row.get("verified")),
                }
                for update, native_row in zip(value["updates"], native_rows)
            ],
            "revision": revision,
        }, "textUpdates"
    elif command_id in {"fusion.image.set", "fusion.macro.apply", "fusion.nested_text.update", "fusion.template.apply", "fusion.text.set"}:
        if command_id == "fusion.image.set":
            body, field = {"timelineItemId": value["timelineItemId"], "imageArtifactId": value["imageArtifactId"], "toolName": str(native.get("tool") or native.get("tool_name") or value.get("groupToolName") or "Loader1"), "inputName": str(native.get("input") or native.get("input_name") or value.get("groupInputName") or "Clip"), "verified": True, "revision": revision}, "imageUpdate"
        elif command_id == "fusion.macro.apply":
            body, field = {"timelineItemId": value["timelineItemId"], "macroName": value["macroName"], "applied": True, "revision": revision}, "macro"
        elif command_id == "fusion.nested_text.update":
            body, field = {"timelineItemId": value["timelineItemId"], "headerUpdated": "header" in value, "bodyUpdated": "body" in value, "revision": revision}, "nestedText"
        elif command_id == "fusion.template.apply":
            body, field = {"timelineItemId": value["timelineItemId"], "template": value["template"], "applied": True, "revision": revision}, "application"
        else:
            body, field = {"timelineItemId": value["timelineItemId"], "toolName": str(native.get("tool") or value.get("toolName") or "TextPlus1"), "inputName": str(native.get("input") or "StyledText"), "text": value["text"], "styled": bool(value.get("styled")), "verified": True, "revision": revision}, "textUpdate"
    elif command_id in {"fusion.generate", "fusion.template.package_drfx"}:
        artifact_id = value["destinationArtifactId"]
        byte_count, digest = output_artifact()
        body, field = {"artifactId": artifact_id, "byteCount": byte_count, "sha256": digest, "mediaType": "application/x-fusion-setting" if command_id == "fusion.generate" else "application/zip"}, "generatedSetting" if command_id == "fusion.generate" else "package"
    elif command_id == "fusion.setting.inspect":
        tools = []
        for row in native.get("tools", []):
            tools.append({"name": str(row.get("name") or row.get("id") or "Tool"), "type": str(row.get("type") or row.get("class") or "Unknown"), "inputCount": len(row.get("inputs") or {})})
        body, field = {"artifactId": value["artifactId"], "tools": tools, "warnings": [str(row.get("message") if isinstance(row, Mapping) else row) for row in native.get("warnings", [])][:256]}, "inspection"
    elif command_id == "fusion.setting.summary":
        body, field = {"artifactId": value["artifactId"], "toolCount": int(native.get("tool_count", sum(native.get("class_counts", {}).values()))), "connectionCount": len(native.get("connections") or []), "animatedInputCount": len(native.get("animated_inputs") or [])}, "summary"
    elif command_id == "fusion.setting.validate":
        static = native.get("static_validation") if isinstance(native.get("static_validation"), Mapping) else native
        body, field = {"artifactId": value["artifactId"], "valid": bool(static.get("valid")), "errors": [str(row.get("message") if isinstance(row, Mapping) else row) for row in static.get("errors", [])][:256], "warnings": [str(row.get("message") if isinstance(row, Mapping) else row) for row in static.get("warnings", [])][:256], "runtimeValidated": False}, "validation"
    elif command_id in {"fusion.template.validate", "lut.validate"}:
        body = {"artifactId": value["artifactId"], "valid": bool(native.get("valid")), "errors": [str(row.get("message") if isinstance(row, Mapping) else row) for row in native.get("errors", [])][:256], "warnings": [str(row.get("message") if isinstance(row, Mapping) else row) for row in native.get("warnings", [])][:256]}
        if command_id == "lut.validate":
            body = {"artifactId": value["artifactId"], "valid": bool(native.get("valid")), "sizeDeclaration": native.get("size") or native.get("size_declaration")}
        field = "validation"
    elif command_id == "lut.inspect":
        body, field = {"artifactId": value["artifactId"], "valid": bool(native.get("valid")), "sizeDeclaration": native.get("size") or native.get("size_declaration"), "entryCount": int(native.get("entries") or native.get("entry_count") or 0)}, "lut"
    elif command_id == "fusion.template.assets.list":
        rows = native.get("assets") if isinstance(native, Mapping) else native
        body, field = [{"name": str(row.get("name") or Path(str(row.get("path") or "asset")).name), "artifactId": str(row.get("artifact_id") or row.get("artifactId"))} for row in rows or []], "assets"
    elif command_id == "fusion.template.assets.add":
        body, field = {"templateArtifactId": value["templateArtifactId"], "assetArtifactId": value["assetArtifactId"], "installedAssetArtifactId": str(native["artifactId"]), "overwritten": copied_overwrite_truth()}, "asset"
    elif command_id == "fusion.template.dir":
        before_configuration = before.get("configuration_RESOLVE_TEMPLATE_DIR", {})
        after_configuration = after.get("configuration_RESOLVE_TEMPLATE_DIR", {})
        body, field = {
            "directoryArtifactId": value["directoryArtifactId"],
            "changed": before_configuration.get("value") != after_configuration.get("value"),
        }, "templateDirectory"
    elif command_id == "fusion.template.icon.set":
        body, field = {"template": value["template"], "sourceArtifactId": value["pngArtifactId"], "installedArtifactId": str(native["artifactId"]), "overwritten": copied_overwrite_truth()}, "icon"
    elif command_id == "fusion.template.install":
        destination = native.get("destination")
        if not isinstance(destination, str):
            raise InventoryValidationError("template install result has no exact destination")
        body, field = {"template": {"name": Path(destination).stem, "kind": value["kind"]}, "overwritten": copied_overwrite_truth()}, "installation"
    elif command_id == "fusion.template.scaffold":
        byte_count, digest = output_artifact()
        body, field = {
            "template": {"name": value["name"], "kind": value["kind"]},
            "created": True,
            "artifactId": value["destinationArtifactId"],
            "byteCount": byte_count,
            "sha256": digest,
        }, "template"
    elif command_id == "fusion.template.uninstall":
        body, field = {"name": value["name"], "kind": value["kind"], "removed": True}, "uninstall"
    elif command_id == "fusion.template.show":
        body, field = {"name": value["name"], "artifactId": native["artifactId"]}, "template"
    elif command_id == "lut.convert":
        body, field = {"sourceArtifactId": value["sourceArtifactId"], "targetFormat": "cube", "converted": False, "valid": bool(native.get("valid"))}, "conversion"
    elif command_id == "lut.generate.identity":
        byte_count, digest = output_artifact()
        body, field = {
            "artifactId": value["destinationArtifactId"],
            "cubeSize": value["cubeSize"],
            "overwritten": overwritten,
            "byteCount": byte_count,
            "sha256": digest,
        }, "generatedLut"
    elif command_id == "lut.install":
        body, field = {"sourceArtifactId": value["sourceArtifactId"], "installedArtifactId": native["artifactId"], "overwritten": copied_overwrite_truth()}, "installation"
    elif command_id == "fusion.tool.registry":
        body, field = deepcopy(dict(native)), "registry"
    elif command_id == "lut.list":
        body, field = deepcopy(list(native.get("luts") or [])), "luts"
    elif command_id == "lut.remove":
        body, field = {"installedArtifactId": value["installedArtifactId"], "status": "removed" if native.get("removed") else "not_found"}, "removal"
    else:
        raise InventoryValidationError(f"Fusion public projection is missing for {command_id}")
    return {"actionId": action_id, field: body}


@dataclass(frozen=True)
class FusionPreparedActionDescriptor:
    command_id: str
    runtime: Any

    version = 1

    @property
    def capability_id(self) -> str:
        return _capability_id(self.command_id)

    @property
    def action_id(self) -> str:
        return f"cutagent.action.{self.command_id}"

    @property
    def operation_class(self) -> str:
        # Packet0 admits only read/mutation. The packet ledger separately keeps
        # render's public long-running execution classification.
        return "read" if self.command_id in _READ_COMMANDS else "mutation"

    @property
    def public_operation_class(self) -> str:
        return "long_running" if self.command_id == "fusion.comp.render" else self.operation_class

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise InventoryValidationError("Fusion action input must be an object")
        schema, _ = _schemas(self.action_id, self.command_id)
        _validate(value, schema, "input")
        if self.command_id == "fusion.nested_text.batch" and any(
            "header" not in update and "body" not in update
            for update in value.get("updates", ())
        ):
            raise InventoryValidationError("Each nested Fusion text update requires header or body text")
        return deepcopy(dict(value))

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        observation = self.runtime.inspect(context, self.command_id, value)
        handler_lowering = self.runtime.prepare_lowering(
            context, self.command_id, value, observation.get("locator") or {}
        )
        targets = deepcopy(list(observation["targets"]))
        pre_state = deepcopy(dict(observation["preState"]))
        if self.command_id in {"fusion.node.add", "fusion.tool.add"} and value.get("flowPosition") is not None and pre_state.get("flowViewAvailable") is False:
            raise InventoryValidationError("Explicit node placement requires an available Fusion flow view. Omit flowPosition for automatic placement.")
        if self.operation_class == "read":
            impact = {
                "contractVersion": 1,
                "status": "read",
                "complete": True,
                "targetDigests": [_digest(target) for target in targets],
                "resultMaximumBytes": 8 * 1024 * 1024,
            }
            minimum = list(fusion_minimum_evidence(self.command_id, self.operation_class))
        else:
            timeline_bound = isinstance(value.get("timelineId"), str)
            project_bound = isinstance(value.get("projectId"), str)
            minimum_binding = "project+timeline" if timeline_bound else "project" if project_bound else "account/project-library"
            minimum = list(fusion_minimum_evidence(self.command_id, self.operation_class))
            referenced_payload_digests = _artifact_digests(context, value, self.runtime)
            template_digest = observation.get("locator", {}).get("templateDigest")
            if self.command_id == "fusion.template.apply" and isinstance(template_digest, str):
                referenced_payload_digests = sorted({
                    *referenced_payload_digests,
                    f"sha256:{template_digest.removeprefix('sha256:')}",
                })
            carrier_base = context.get("mutationBase")
            if not isinstance(carrier_base, Mapping) or (
                carrier_base.get("contractVersion") != 1
                or carrier_base.get("carrier") != "sdk"
                or carrier_base.get("minimumBinding") != minimum_binding
                or sorted(carrier_base.get("referencedPayloadDigests") or [])
                != referenced_payload_digests
            ):
                raise InventoryValidationError(
                    "Fusion mutation carrier binding disagrees with exact domain custody"
                )
            impact = deepcopy(dict(carrier_base))
            impact.update({
                "status": "mutation",
                "effects": [{
                    "operation": self.command_id,
                    "kind": _operation_kind(self.command_id),
                    "trackTypes": [],
                    "targets": _mutation_targets(context, targets),
                    "placementIntent": "explicit",
                    "broad": False,
                    "ambiguous": False,
                    "complete": True,
                }],
                "closedComposition": True,
                "complete": True,
                "ambiguous": False,
                "broad": False,
                "executableStableTargetPrecondition": True,
                "verificationPolicy": {
                    "minimumEvidence": minimum,
                    "requireProtectedStatePreserved": True,
                    "protectedTargetEvidence": "every_declared_target",
                },
            })
        return {
            "targets": targets,
            "preState": pre_state,
            "impact": impact,
            "lowering": {
                "normalizedInput": deepcopy(dict(value)),
                "locator": deepcopy(dict(observation.get("locator") or {})),
                **deepcopy(dict(handler_lowering)),
            },
            "verification": {"minimumEvidence": minimum},
            "recovery": {"strategy": "project_checkpoint_or_managed_artifact_restore" if self.operation_class != "read" else "not_applicable"},
        }

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise InventoryValidationError("prepared Fusion input is unavailable")
        observation = self.runtime.inspect(context, self.command_id, value)
        return {"targets": deepcopy(list(observation["targets"])), "preState": deepcopy(dict(observation["preState"]))}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Mapping[str, Any]:
        value = prepared["lowering"]["normalizedInput"]
        private_result = self.runtime.execute(context, self.command_id, value, prepared)
        public_result = _public_projection(self.command_id, value, private_result)
        if not self.validate_public_result(public_result):
            raise InventoryValidationError("Fusion runtime returned an invalid public result")
        self.runtime.stage_private_result(context, private_result)
        return public_result

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        if not isinstance(result, Mapping) or not self.validate_public_result(result):
            raise InventoryValidationError("Fusion runtime returned an invalid public result")
        private_result = self.runtime.private_result(context)
        verification = self.runtime.verify(
            context, self.command_id, prepared["lowering"]["normalizedInput"], prepared, private_result
        )
        if verification.get("outcome") == "passed":
            self.runtime.finalize(context)
        return verification

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        return self.runtime.recover(context, self.command_id, prepared["lowering"]["normalizedInput"])

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        if not isinstance(result, Mapping):
            raise InventoryValidationError("Fusion runtime projection source is invalid")
        # Packet0 currently returns execute() directly. This identity projection
        # keeps the descriptor compatible when the owner begins invoking all
        # eight stages, without exposing the private before/after envelope.
        public = deepcopy(dict(result))
        if not self.validate_public_result(public):
            raise InventoryValidationError("Fusion runtime projection is invalid")
        return public

    def validate_public_result(self, value: Any) -> bool:
        _, schema = _schemas(self.action_id, self.command_id)
        try:
            _validate(value, schema, "result")
        except InventoryValidationError:
            return False
        return True


def fusion_prepared_action_descriptors(
    runtime: Any | None = None,
) -> Mapping[str, FusionPreparedActionDescriptor]:
    concrete = runtime or _LazyFusionPreparedActionRuntime()
    excluded = set(DELEGATED_ACTIONS) | set(UNAVAILABLE_ACTIONS)
    return MappingProxyType({
        f"cutagent.action.{command_id}": FusionPreparedActionDescriptor(command_id, concrete)
        for command_id in sorted(_ALL_COMMAND_IDS)
        if f"cutagent.action.{command_id}" not in excluded
    })


def fusion_prepared_action_contribution(
    runtime: Any | None = None,
) -> tuple[str, Mapping[str, Any]]:
    contribution: dict[str, Any] = dict(fusion_prepared_action_descriptors(runtime))
    contribution.update({action_id: object() for action_id in UNAVAILABLE_ACTIONS})
    return "fusion_dctl_lut", MappingProxyType(contribution)


def register_fusion_prepared_actions(registry: Any, runtime: Any | None = None) -> None:
    registry.register_contribution(*fusion_prepared_action_contribution(runtime))
