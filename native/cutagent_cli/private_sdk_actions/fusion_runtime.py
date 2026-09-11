"""Exact-target runtime for prepared Fusion, DCTL, and LUT actions.

The signed prepared-action authority is the only caller. Public action input is
validated before this module runs; local paths, native objects, command handlers,
checkpoints, and graph evidence remain private here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any, Mapping

from typer.models import ArgumentInfo, OptionInfo

from ..connection import get_connection
from ..core import fusion_api, fusion_image_ops, sdk_live_inspection, sdk_tools, version_ops
from ..errors import APICallFailed
from .errors import FusionDescriptorValidationError as InventoryValidationError
from .fusion_evidence import fusion_emitted_evidence


_HANDLER_LOCK = threading.RLock()
_GRAPH_COMMANDS = frozenset({
    "fusion.comp.render", "fusion.tool.paste",
    "fusion.comp.current", "fusion.keyframe.list", "fusion.tool.attrs",
    "fusion.tool.get", "fusion.tool.inputs", "fusion.tool.list", "fusion.tool.outputs",
    "fusion.image.set", "fusion.macro.apply", "fusion.nested_text.update",
    "fusion.template.apply", "fusion.text.set",
    "fusion.comp.range",
    "fusion.effect.blur", "fusion.effect.color_correct", "fusion.effect.glow",
    "fusion.effect.sharpen", "fusion.effect.transform", "fusion.keyer.chroma",
    "fusion.keyframe.add", "fusion.keyframe.clear", "fusion.keyframe.delete",
    "fusion.keyframe.set", "fusion.mask.ellipse", "fusion.mask.polygon",
    "fusion.mask.rectangle", "fusion.node.add", "fusion.node.connect",
    "fusion.node.delete", "fusion.node.disconnect", "fusion.tool.active",
    "fusion.tool.add", "fusion.tool.connect", "fusion.tool.delete",
    "fusion.tool.disconnect", "fusion.tool.set", "fusion.tracker.add",
})
_ITEM_COMMANDS = frozenset({
    "fusion.comp.delete", "fusion.comp.rename", "fusion.image.set",
    "fusion.macro.apply", "fusion.nested_text.update", "fusion.template.apply",
    "fusion.text.batch", "fusion.text.set", "dctl.apply",
})
_ARTIFACT_READ_COMMANDS = frozenset({
    "fusion.setting.inspect", "fusion.setting.summary", "fusion.setting.validate",
    "fusion.template.assets.list", "fusion.template.validate", "lut.convert", "lut.inspect",
    "lut.validate",
})
_OFFLINE_COMMANDS = frozenset({
    "fusion.setting.center_to_polypath", "fusion.setting.polypath_to_center",
})
_FILESYSTEM_COMMANDS = frozenset({
    "fusion.generate", "fusion.template.assets.add", "fusion.template.dir",
    "fusion.template.icon.set", "fusion.template.install",
    "fusion.template.package_drfx", "fusion.template.scaffold",
    "fusion.template.uninstall", "lut.generate.identity", "lut.install", "lut.remove",
})
_READ_COMMANDS = frozenset({
    "fusion.comp.current", "fusion.keyframe.list", "fusion.setting.center_to_polypath",
    "fusion.setting.inspect", "fusion.setting.polypath_to_center", "fusion.setting.summary",
    "fusion.template.assets.list", "fusion.template.show", "fusion.template.validate",
    "fusion.tool.attrs", "fusion.tool.get", "fusion.tool.inputs", "fusion.tool.list",
    "fusion.tool.registry", "fusion.tool.outputs", "lut.convert", "lut.inspect", "lut.list", "lut.validate",
})
_LIVE_HANDLER_COMMANDS = frozenset({
    "fusion.image.set", "fusion.insert_setting", "fusion.macro.apply",
    "fusion.nested_text.batch", "fusion.nested_text.update", "fusion.template.apply", "fusion.text.batch", "fusion.text.set",
})
_CREATE_TOOL_TYPES = {
    "fusion.effect.blur": "Blur",
    "fusion.effect.color_correct": "ColorCorrector",
    "fusion.effect.glow": "SoftGlow",
    "fusion.effect.sharpen": "UnsharpMask",
    "fusion.effect.transform": "Transform",
    "fusion.keyer.chroma": "DeltaKeyer",
    "fusion.mask.ellipse": "EllipseMask",
    "fusion.mask.polygon": "PolylineMask",
    "fusion.mask.rectangle": "RectangleMask",
    "fusion.tracker.add": "Tracker",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"


def _revision(value: Any) -> str:
    return f"revision_{hashlib.sha256(_canonical(value)).hexdigest()}"


def _public_fusion_value(value: Any) -> Any:
    """Project a native Fusion value into the public SDK value union."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value if math.isfinite(float(value)) else None
    if isinstance(value, Mapping) and set(value) == {"x", "y"}:
        x, y = value["x"], value["y"]
        if all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            for item in (x, y)
        ):
            return {"x": float(x), "y": float(y)}
        return None
    if isinstance(value, Mapping):
        normalized = {str(key): item for key, item in value.items()}
        if set(normalized) in ({"1", "2"}, {"1", "2", "3"}, {"1", "2", "3", "4"}):
            ordered = [normalized[str(index)] for index in range(1, len(normalized) + 1)]
            if all(
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and math.isfinite(float(item))
                for item in ordered
            ):
                return ordered
        return None
    if isinstance(value, (list, tuple)) and len(value) <= 16 and all(
        isinstance(item, (int, float))
        and not isinstance(item, bool)
        and math.isfinite(float(item))
        for item in value
    ):
        return list(value)
    # Connected image streams and other PyRemoteObject values are native graph
    # handles, not members of the public scalar/point/number-array contract.
    return None


def _materialized_default(parameter: inspect.Parameter) -> Any:
    default = parameter.default
    if isinstance(default, (ArgumentInfo, OptionInfo)):
        candidate = default.default
        if candidate is ...:
            raise InventoryValidationError(f"required private handler parameter is missing: {parameter.name}")
        return deepcopy(candidate)
    if default is inspect.Parameter.empty:
        raise InventoryValidationError(f"required private handler parameter is missing: {parameter.name}")
    return deepcopy(default)


class FusionArtifactCustody:
    """Private origin-bound custody for handler-produced filesystem artifacts."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def record(self, artifact_id: str) -> Mapping[str, Any] | None:
        return self._records.get(artifact_id)

    @staticmethod
    def _identity(context: Mapping[str, Any], source: str, *, stable_namespace: bool) -> tuple[Path, bytes, str, str]:
        path = Path(source)
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            raise InventoryValidationError("handler output cannot enter managed artifact custody")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        origin = str(path.resolve())
        namespace = context.get("privateArtifactCustodyNamespace") if stable_namespace else context.get("privateArtifactStoreRoot")
        if stable_namespace:
            if not isinstance(namespace, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", namespace):
                raise InventoryValidationError("signed SDK session has no stable artifact custody namespace")
        elif not isinstance(namespace, str) or not Path(namespace).is_absolute():
            raise InventoryValidationError("signed SDK session has no private artifact store")
        identity = hashlib.sha256(_canonical({
            "sha256": digest,
            "originPath": origin,
            "custodyNamespace": namespace,
        })).hexdigest()
        return path, raw, digest, f"artifact_{identity}"

    @staticmethod
    def identify(context: Mapping[str, Any], source: str, *, stable_namespace: bool = False) -> str:
        return FusionArtifactCustody._identity(context, source, stable_namespace=stable_namespace)[3]

    def adopt(self, context: Mapping[str, Any], source: str, *, stable_namespace: bool = False) -> str:
        path, raw, digest, artifact_id = self._identity(context, source, stable_namespace=stable_namespace)
        origin = str(path.resolve())
        root_value = context.get("privateArtifactStoreRoot")
        if not isinstance(root_value, str) or not Path(root_value).is_absolute():
            raise InventoryValidationError("signed SDK session has no private artifact store")
        root_input = Path(root_value)
        if root_input.is_symlink():
            raise InventoryValidationError("private artifact store root is unsafe")
        root = root_input.resolve()
        root.mkdir(parents=True, exist_ok=True)
        artifact_root = root / artifact_id
        if artifact_root.is_symlink() or (artifact_root.exists() and not artifact_root.is_dir()):
            raise InventoryValidationError("managed artifact directory is unsafe")
        artifact_root.mkdir(exist_ok=True)
        resolved_artifact_root = artifact_root.resolve()
        if resolved_artifact_root.parent != root:
            raise InventoryValidationError("managed artifact directory escaped private custody")
        destination = resolved_artifact_root / path.name
        if destination.resolve(strict=False).parent != resolved_artifact_root:
            raise InventoryValidationError("managed artifact destination escaped private custody")
        if destination.exists():
            if (
                destination.is_symlink()
                or not destination.is_file()
                or hashlib.sha256(destination.read_bytes()).hexdigest() != digest
            ):
                raise InventoryValidationError("managed artifact destination changed after adoption")
        else:
            destination.write_bytes(raw)
        self._records[artifact_id] = {
            "path": str(destination), "originPath": origin,
            "sha256": digest, "byteCount": len(raw),
        }
        return artifact_id


def _managed_record(context: Mapping[str, Any], artifact_id: str) -> Mapping[str, Any]:
    records = context.get("privateManagedArtifacts")
    record = records.get(artifact_id) if isinstance(records, Mapping) else None
    custody = context.get("_fusionArtifactCustody")
    if not isinstance(record, Mapping) and isinstance(custody, FusionArtifactCustody):
        record = custody.record(artifact_id)
    path = record.get("path") if isinstance(record, Mapping) else None
    if not isinstance(record, Mapping) or not isinstance(path, str) or not Path(path).is_absolute():
        raise InventoryValidationError("managed artifact is not bound to this signed SDK session")
    return record


def _managed_path(
    context: Mapping[str, Any], artifact_id: str, *, existing: bool | None = True,
    require_reservation: bool = False,
) -> str:
    record = _managed_record(context, artifact_id)
    path = Path(str(record["path"]))
    if require_reservation or existing is False:
        reservation = record.get("reservationId")
        if not isinstance(reservation, str) or not reservation:
            raise InventoryValidationError("managed output artifact has no destination reservation")
    if existing is True:
        if not path.exists() or path.is_symlink():
            raise InventoryValidationError("managed input artifact is missing or unsafe")
        expected = record.get("sha256")
        if path.is_file() and not isinstance(expected, str):
            raise InventoryValidationError("managed input artifact has no bound digest")
        if path.is_file():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected.removeprefix("sha256:") != actual:
                raise InventoryValidationError("managed input artifact digest changed")
    elif existing is False:
        if path.exists() and not bool(record.get("overwrite")):
            raise InventoryValidationError("managed output artifact already exists")
    return str(path)


def _artifact_state(context: Mapping[str, Any], artifact_id: str) -> dict[str, Any]:
    path = Path(_managed_path(context, artifact_id, existing=True))
    return _path_state(path)


def _path_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"kind": "absent", "digest": _digest({"absent": True})}
    if path.is_symlink():
        raise InventoryValidationError("artifact path is an unsafe symlink")
    if path.is_dir():
        rows = []
        for child in sorted(path.rglob("*")):
            if child.is_symlink():
                raise InventoryValidationError("managed artifact directory contains a symlink")
            if child.is_file():
                rows.append({
                    "name": child.relative_to(path).as_posix(),
                    "size": child.stat().st_size,
                    "sha256": hashlib.sha256(child.read_bytes()).hexdigest(),
                })
        return {"kind": "directory", "entries": rows, "digest": _digest(rows)}
    raw = path.read_bytes()
    return {
        "kind": "file",
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "digest": f"sha256:{hashlib.sha256(raw).hexdigest()}",
    }


def _binding_native_id(context: Mapping[str, Any], public_id: str) -> str:
    bindings = context.get("privateTargetBindings")
    binding = bindings.get(public_id) if isinstance(bindings, Mapping) else None
    if not isinstance(binding, Mapping) or binding.get("kind") not in {"clip", "timeline_item"}:
        raise InventoryValidationError("timeline item is not privately bound to this SDK session")
    native_id = binding.get("nativeId") or binding.get("selector")
    if not isinstance(native_id, str) or not native_id:
        raise InventoryValidationError("timeline item binding has no exact native identity")
    return native_id


def _find_item(conn: Any, context: Mapping[str, Any], public_id: str) -> tuple[Any, int, int]:
    native_id = _binding_native_id(context, public_id)
    matches: list[tuple[Any, int, int]] = []
    track_count = int(conn.timeline.GetTrackCount("video") or 0)
    for track_index in range(1, track_count + 1):
        for item in conn.timeline.GetItemListInTrack("video", track_index) or []:
            if sdk_live_inspection.documented_unique_id(item) == native_id:
                matches.append((item, track_index, int(item.GetStart())))
    if len(matches) != 1:
        raise InventoryValidationError("exact Fusion timeline item is missing or ambiguous")
    return matches[0]


def _composition(item: Any, index: int) -> Any:
    if not isinstance(index, int) or isinstance(index, bool) or not 1 <= index <= 128:
        raise InventoryValidationError("Fusion composition index is invalid")
    comp = item.GetFusionCompByIndex(index)
    if comp is None:
        raise InventoryValidationError("exact Fusion composition no longer exists")
    return comp


def _composition_name(item: Any, index: int, attrs: Mapping[str, Any] | None = None) -> str:
    names = item.GetFusionCompNameList() or []
    if isinstance(names, (list, tuple)) and index <= len(names):
        name = str(names[index - 1] or "")
        if name:
            return name
    attrs = attrs or {}
    name = str(attrs.get("COMPS_Name") or attrs.get("COMPN_Name") or "")
    if not name:
        raise APICallFailed("Fusion composition has no stable name")
    return name


def _timeline_item_range(item: Any, record_start: int) -> dict[str, int]:
    try:
        record_end = int(item.GetEnd())
        duration = int(item.GetDuration())
        source_start = int(item.GetLeftOffset())
    except (AttributeError, TypeError, ValueError) as exc:
        raise InventoryValidationError("Fusion timeline item range is not exactly readable") from exc
    if duration < 1 or record_end - record_start != duration or source_start < 0:
        raise InventoryValidationError("Fusion timeline item range is inconsistent")
    return {
        "recordStart": record_start,
        "recordEndExclusive": record_end,
        "sourceStart": source_start,
        "sourceEndExclusive": source_start + duration,
    }


def _composition_range_lowering(
    value: Mapping[str, Any], locator: Mapping[str, Any]
) -> dict[str, int]:
    item_range = locator.get("timelineItemRange")
    if not isinstance(item_range, Mapping):
        raise InventoryValidationError("Fusion composition range has no exact timeline item range")
    record_start = item_range.get("recordStart")
    record_end = item_range.get("recordEndExclusive")
    if (
        not isinstance(record_start, int)
        or isinstance(record_start, bool)
        or not isinstance(record_end, int)
        or isinstance(record_end, bool)
    ):
        raise InventoryValidationError("Fusion composition range has invalid timeline item geometry")
    requested = value.get("range")
    if not isinstance(requested, Mapping):
        raise InventoryValidationError("Fusion composition range is invalid")
    start = requested.get("start")
    end_exclusive = requested.get("endExclusive")
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end_exclusive, int)
        or isinstance(end_exclusive, bool)
        or not record_start <= start < end_exclusive <= record_end
    ):
        raise InventoryValidationError("Fusion composition range is outside the timeline item")
    return {
        "start": start - record_start,
        "end": end_exclusive - record_start - 1,
    }


def _canonical_fusion_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_fusion_value(nested)
            for key, nested in value.items()
            if str(key) != "__flags"
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_fusion_value(nested) for nested in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _comp_state(comp: Any) -> dict[str, Any]:
    attrs = comp.GetAttrs() or {}
    active_tool_name = _active_tool_name(comp, attrs.get("COMPH_ActiveTool"))
    digest_attrs = dict(attrs)
    if "COMPH_ActiveTool" in digest_attrs:
        digest_attrs["COMPH_ActiveTool"] = active_tool_name
    graph = sdk_live_inspection._fusion_graph_evidence(comp, None)
    tools = comp.GetToolList(False) or {}
    by_name = {}
    for tool in tools.values():
        tool_attrs = tool.GetAttrs() or {}
        by_name[str(tool_attrs.get("TOOLS_Name") or getattr(tool, "Name", ""))] = tool
    for node in graph.get("nodes", ()):
        tool = by_name.get(node.get("name"))
        if tool is not None and node.get("type") == "PolylineMask":
            try:
                bezier = tool.GetBezierPolyline(0)
                if isinstance(bezier, Mapping):
                    node["bezierPolyline"] = _canonical_fusion_value(bezier)
            except Exception:
                pass
    flow_view_available = False
    try:
        flow_view = comp.CurrentFrame.FlowView
        flow_view_available = callable(getattr(flow_view, "GetPosTable", None))
        for node in graph.get("nodes", ()):
            tool = by_name.get(node.get("name"))
            position = flow_view.GetPosTable(tool) if tool is not None else None
            if isinstance(position, Mapping) and 1 in position and 2 in position:
                node["flowPosition"] = {
                    "x": float(position[1]), "y": float(position[2]),
                }
    except Exception:
        # Exact position-dependent actions fail closed when this evidence is absent.
        pass
    rendering = False
    if callable(getattr(comp, "IsRendering", None)):
        rendering = bool(comp.IsRendering())
    elif "COMPB_Rendering" in attrs:
        rendering = bool(attrs["COMPB_Rendering"])
    protected_attrs = {
        key: value for key, value in digest_attrs.items()
        if key not in {"COMPN_RenderStart", "COMPN_RenderEnd"}
    }
    rename_protected_attrs = {
        key: value for key, value in digest_attrs.items()
        if key not in {"COMPS_Name", "COMPN_Name"}
    }
    return {
        "name": str(attrs.get("COMPS_Name") or attrs.get("COMPN_Name") or "Composition"),
        "globalStart": attrs.get("COMPN_GlobalStart"),
        "globalEnd": attrs.get("COMPN_GlobalEnd"),
        "renderStart": attrs.get("COMPN_RenderStart"),
        "renderEnd": attrs.get("COMPN_RenderEnd"),
        "activeTool": active_tool_name,
        "rendering": rendering,
        "graph": graph,
        "flowViewAvailable": flow_view_available,
        "attrsDigest": _digest(digest_attrs),
        "connectionAttrsDigest": _connection_attrs_digest(digest_attrs),
        "protectedDigest": _digest({"attrs": protected_attrs, "graph": graph}),
        "renameProtectedDigest": _digest({"attrs": rename_protected_attrs, "graph": graph}),
        "digest": _digest({"attrs": digest_attrs, "graph": graph}),
    }


def _active_tool_name(comp: Any, native_handle: Any = None) -> str | None:
    tool = getattr(comp, "ActiveTool", None)
    if tool is None:
        tool = getattr(comp, "CurrentTool", None)
    names: list[str] = []
    has_handle = False
    for candidate in (tool, native_handle):
        if candidate is None:
            continue
        has_handle = True
        try:
            attrs = candidate.GetAttrs() if hasattr(candidate, "GetAttrs") else {}
            raw_name = attrs.get("TOOLS_Name") if isinstance(attrs, Mapping) else None
            if not isinstance(raw_name, str) or not raw_name:
                raw_name = getattr(candidate, "Name", "")
            name = raw_name if isinstance(raw_name, str) else ""
        except Exception:
            name = ""
        if name and name not in names:
            names.append(name)
    if len(names) > 1:
        raise InventoryValidationError("Fusion active-tool identity is inconsistent")
    if names:
        return names[0]
    if has_handle:
        raise InventoryValidationError("Fusion active-tool identity is not independently readable")
    return None


def _node_map(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    graph = state.get("graph") if isinstance(state, Mapping) else None
    nodes = graph.get("nodes") if isinstance(graph, Mapping) else None
    return {
        str(node.get("name")): node
        for node in nodes or []
        if isinstance(node, Mapping) and isinstance(node.get("name"), str)
    }


def _input_row(state: Mapping[str, Any], tool_name: str, input_name: str) -> Mapping[str, Any] | None:
    node = _node_map(state).get(tool_name)
    if not isinstance(node, Mapping):
        return None
    return next(
        (row for row in node.get("inputs", []) if isinstance(row, Mapping) and row.get("id") == input_name),
        None,
    )


def _connection_attrs_digest(attrs: Mapping[str, Any]) -> str:
    # A successful topology write marks the composition dirty. All authored
    # attributes, including render ranges and quality, remain protected.
    return _digest({key: value for key, value in attrs.items() if key != "COMPB_Modified"})


def _connection_protected_digest(
    state: Mapping[str, Any], tool_name: str, input_name: str
) -> str | None:
    attrs_digest = state.get("connectionAttrsDigest", state.get("attrsDigest"))
    graph = state.get("graph")
    nodes = graph.get("nodes") if isinstance(graph, Mapping) else None
    if not isinstance(attrs_digest, str) or not isinstance(nodes, list):
        return None
    matched = 0
    projected_nodes: list[Any] = []
    node_names: set[str] = set()
    by_name = _node_map(state)
    for node in nodes:
        if (
            not isinstance(node, Mapping)
            or not isinstance(node.get("name"), str)
            or not node["name"]
            or node["name"] in node_names
        ):
            return None
        node_names.add(node["name"])
        inputs = node.get("inputs")
        if not isinstance(inputs, list):
            return None
        projected_inputs: list[Any] = []
        input_ids: set[str] = set()
        for row in inputs:
            if (
                not isinstance(row, Mapping)
                or not isinstance(row.get("id"), str)
                or not row["id"]
                or row["id"] in input_ids
            ):
                return None
            input_ids.add(row["id"])
            if node["name"] == tool_name and row["id"] == input_name:
                matched += 1
                # Live inspection intentionally suppresses a connected input's
                # scalar value. Connecting therefore changes both fields in the
                # evidence even though the native mutation is only the requested
                # topology edge. Expressions and keyframes remain protected.
                projected = {
                    key: value
                    for key, value in row.items()
                    if key not in {"connection", "value"}
                }
                connection = row.get("connection")
                upstream = (
                    by_name.get(connection.get("node"))
                    if isinstance(connection, Mapping) else None
                )
                if (
                    input_name == "EffectMask"
                    and isinstance(connection, Mapping)
                    and connection.get("port") == "Mask"
                    and isinstance(upstream, Mapping)
                    and upstream.get("type") == "RectangleMask"
                    and row.get("keyframes") in (
                        {1: -1_000_000_000, 2: 1_000_000_000},
                        {"1": -1_000_000_000, "2": 1_000_000_000},
                    )
                ):
                    # Native GetKeyFrames reports this unbounded image-domain
                    # marker after wiring a RectangleMask. It is not an authored
                    # input curve; the upstream tool's real curves stay protected.
                    projected["keyframes"] = {}
                projected_inputs.append(projected)
            else:
                projected_inputs.append(row)
        # GetToolList/GetInputList numeric enumeration changes when wiring tools.
        # Stable tool names and input IDs, not those list indices, define identity.
        projected_nodes.append({
            **{key: value for key, value in node.items() if key != "key"},
            "inputs": sorted(projected_inputs, key=lambda row: row["id"]),
        })
    if matched != 1:
        return None
    return _digest({"attrsDigest": attrs_digest, "graph": {
        **graph, "nodes": sorted(projected_nodes, key=lambda node: node["name"]),
    }})


def _native_values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(actual, Mapping) and isinstance(expected, Mapping):
        normalized_actual = {str(key): item for key, item in actual.items()}
        normalized_expected = {str(key): item for key, item in expected.items()}
        return normalized_actual.keys() == normalized_expected.keys() and all(
            _native_values_equal(normalized_actual[key], normalized_expected[key])
            for key in normalized_actual
        )
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(
            _native_values_equal(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def _created_tool_expectation(
    command_id: str, value: Mapping[str, Any]
) -> tuple[dict[str, Any], bool]:
    point = lambda field, default: value.get(field, default)
    if command_id == "fusion.effect.blur":
        strength = float(value.get("blurStrength", 5.0))
        return {"XBlurSize": strength, "YBlurSize": strength}, True
    if command_id == "fusion.effect.glow":
        return {"Gain": float(value.get("intensity", 0.5))}, True
    if command_id == "fusion.effect.sharpen":
        amount = float(value.get("amount", 0.5))
        return {"XSize": amount, "YSize": amount}, True
    if command_id == "fusion.effect.transform":
        position = point("position", {"x": 0.0, "y": 0.0})
        return {
            "Size": float(value.get("zoom", 1.0)),
            "Center": {1: 0.5 + float(position["x"]), 2: 0.5 + float(position["y"]), 3: 0.0},
            "Angle": float(value.get("rotationDegrees", 0.0)),
        }, True
    if command_id == "fusion.effect.color_correct":
        return {
            "MasterRGBGain": 1.0,
            "MasterRedGain": float(value.get("redGain", 1.0)),
            "MasterGreenGain": float(value.get("greenGain", 1.0)),
            "MasterBlueGain": float(value.get("blueGain", 1.0)),
            "MasterRGBGamma": float(value.get("gamma", 1.0)),
            "Saturation1": float(value.get("saturation", 1.0)),
        }, True
    if command_id == "fusion.keyer.chroma":
        colors = {
            "green": {1: 0.0, 2: 1.0, 3: 0.0},
            "blue": {1: 0.0, 2: 0.0, 3: 1.0},
            "red": {1: 1.0, 2: 0.0, 3: 0.0},
        }
        color = colors[str(value.get("keyColor", "green"))]
        return {
            "BackgroundRed": color[1],
            "BackgroundGreen": color[2],
            "BackgroundBlue": color[3],
            "LowThreshold": float(value.get("threshold", 0.3)),
        }, True
    if command_id in {"fusion.mask.ellipse", "fusion.mask.rectangle"}:
        center = point("center", {"x": 0.5, "y": 0.5})
        return {
            "Center": {1: float(center["x"]), 2: float(center["y"]), 3: 0.0},
            "Width": float(value.get("width", 0.5)),
            "Height": float(value.get("height", 0.5)),
            "SoftEdge": float(value.get("softness", 0.0)),
        }, False
    if command_id == "fusion.mask.polygon":
        return {}, False
    if command_id == "fusion.tracker.add":
        center = point("patternCenter", {"x": 0.5, "y": 0.5})
        return {"PatternCenter1": {1: float(center["x"]), 2: float(center["y"]), 3: 0.0}}, True
    raise InventoryValidationError("unknown created Fusion tool verification contract")


def _verify_created_tool(
    command_id: str,
    value: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> bool:
    before_nodes = _node_map(before)
    after_nodes = _node_map(after)
    added = set(after_nodes) - set(before_nodes)
    if len(added) != 1:
        return False
    name = next(iter(added))
    node = after_nodes[name]
    if node.get("type") != _CREATE_TOOL_TYPES[command_id]:
        return False
    if command_id == "fusion.mask.polygon":
        bezier = node.get("bezierPolyline")
        polyline = bezier.get("Value") if isinstance(bezier, Mapping) else None
        points = polyline.get("Points") if isinstance(polyline, Mapping) else None
        if not isinstance(points, Mapping) or polyline.get("Closed") is not True:
            return False
        try:
            observed = [
                {"x": float(row["X"]), "y": float(row["Y"])}
                for _, row in sorted(
                    ((float(key), row) for key, row in points.items() if key != "__flags"),
                    key=lambda entry: entry[0],
                )
            ]
        except (KeyError, TypeError, ValueError):
            return False
        if observed != [
            {"x": float(row["x"]), "y": float(row["y"])}
            for row in value["points"]
        ]:
            return False
    expected_inputs, inline = _created_tool_expectation(command_id, value)
    for input_name, expected in expected_inputs.items():
        row = _input_row(after, name, input_name)
        if not isinstance(row, Mapping) or not _native_values_equal(row.get("value"), expected):
            return False
    if not inline:
        return True
    before_connections = {
        (node_name, str(row.get("id"))): row.get("connection")
        for node_name, existing_node in before_nodes.items()
        for row in existing_node.get("inputs", ())
        if isinstance(row, Mapping)
    }
    after_connections = {
        (node_name, str(row.get("id"))): row.get("connection")
        for node_name, existing_node in after_nodes.items()
        if node_name != name
        for row in existing_node.get("inputs", ())
        if isinstance(row, Mapping)
    }
    if before_connections.keys() != after_connections.keys():
        return False
    changed = [
        key for key in before_connections
        if before_connections[key] != after_connections[key]
    ]
    if len(changed) != 1:
        return False
    downstream_name, _ = changed[0]
    upstream = before_connections[changed[0]]
    replacement = after_connections[changed[0]]
    if (
        after_nodes[downstream_name].get("type") != "MediaOut"
        or not isinstance(upstream, Mapping)
        or not isinstance(replacement, Mapping)
        or replacement.get("node") != name
    ):
        return False
    return any(
        isinstance(row, Mapping) and row.get("connection") == upstream
        for row in node.get("inputs", ())
    )


class _ExactFusionAPI(fusion_api.FusionAPI):
    def __init__(self, conn: Any, comp: Any):
        super().__init__(conn)
        self._exact_comp = comp

    @property
    def comp(self):
        return self._exact_comp


@dataclass
class _ExecutionCheckpoint:
    checkpoint_id: str | None
    filesystem_backup: dict[str, bytes | None]
    template_dir_before: str | None = None
    created_directories: tuple[str, ...] = ()


class FusionPreparedActionRuntime:
    """Production backend that binds descriptors to existing CutAgent CLI handlers."""

    def __init__(self, custody: FusionArtifactCustody | None = None):
        self._checkpoints: dict[str, _ExecutionCheckpoint] = {}
        self._private_results: dict[str, Mapping[str, Any]] = {}
        self._checkpoint_lock = threading.RLock()
        self._custody = custody or FusionArtifactCustody()

    def _bound(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        return {**context, "_fusionArtifactCustody": self._custody}

    def managed_artifact_record(self, context: Mapping[str, Any], artifact_id: str) -> Mapping[str, Any] | None:
        try:
            return _managed_record(self._bound(context), artifact_id)
        except InventoryValidationError:
            return None

    @staticmethod
    def _execution_id(context: Mapping[str, Any]) -> str:
        execution_id = str(context.get("executionId") or context.get("execution", {}).get("executionId") or "")
        if not execution_id:
            raise InventoryValidationError("prepared Fusion execution has no execution identity")
        return execution_id

    def stage_private_result(self, context: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        with self._checkpoint_lock:
            self._private_results[self._execution_id(context)] = deepcopy(dict(result))

    def private_result(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        with self._checkpoint_lock:
            result = self._private_results.get(self._execution_id(context))
        if result is None:
            raise InventoryValidationError("prepared Fusion private result is unavailable")
        return deepcopy(dict(result))

    def finalize(self, context: Mapping[str, Any]) -> None:
        execution_id = self._execution_id(context)
        with self._checkpoint_lock:
            self._private_results.pop(execution_id, None)
            self._checkpoints.pop(execution_id, None)

    def prepare_lowering(
        self, context: Mapping[str, Any], command_id: str, value: Mapping[str, Any], locator: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if command_id == "fusion.insert_settings.batch":
            common = {key: value[key] for key in ("projectId", "timelineId", "revision")}
            return {
                "itemLowerings": [
                    self.prepare_lowering(
                        context,
                        "fusion.insert_setting",
                        {**common, **dict(item)},
                        {},
                    )
                    for item in value["items"]
                ]
            }
        if command_id in (_OFFLINE_COMMANDS | {"fusion.image.batch", "fusion.tool.registry", "lut.list", "fusion.tool.inputs", "dctl.apply", "lut_refresh", "fusion.comp.delete", "fusion.comp.rename", "fusion.nested_text.batch"}):
            return {}
        module, function_name = self._handler(command_id)
        handler = getattr(module, function_name)
        while hasattr(handler, "__wrapped__"):
            handler = handler.__wrapped__
        prepared = {"lowering": {"locator": deepcopy(dict(locator))}}
        return {
            "handlerName": function_name,
            "handlerKwargs": self._handler_kwargs(self._bound(context), command_id, value, prepared, handler),
        }

    @staticmethod
    def _inspect_nested_text_update(
        conn: Any, context: Mapping[str, Any], value: Mapping[str, Any]
    ) -> dict[str, Any]:
        public_item_id = str(value["timelineItemId"])
        item, track_index, record_frame = _find_item(conn, context, public_item_id)
        from ..commands import fusion as fusion_commands

        open_state = fusion_commands._open_nested_timeline(conn, item)
        try:
            text_items = fusion_commands._collect_nested_text_items(
                open_state["nested_timeline"]
            )
            header_row, body_row = fusion_commands._select_nested_text_targets(
                text_items,
                header_clip_name=value.get("headerClipName"),
                body_clip_name=value.get("bodyClipName"),
            )

            def role_state(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
                if row is None:
                    return None
                nested_item = row["item"]
                comp = _composition(nested_item, 1)
                return {
                    "clipName": row.get("name"),
                    "trackIndex": row.get("track_index"),
                    "composition": _comp_state(comp),
                }

            state = {
                "compoundNativeId": sdk_live_inspection.documented_unique_id(item),
                "header": role_state(header_row),
                "body": role_state(body_row),
            }
            state["digest"] = _digest(state)
        finally:
            fusion_commands._restore_original_timeline(
                open_state["project"], open_state["original_timeline"]
            )
            try:
                conn.timeline = open_state["original_timeline"]
            except Exception:
                pass

        return {
            "targets": [{
                "kind": "timeline_item",
                "stableId": public_item_id,
                "revision": state["digest"],
            }],
            "preState": state,
            "locator": {
                "timelineItemId": public_item_id,
                "trackIndex": track_index,
                "recordFrame": record_frame,
                "clipName": str(item.GetName() or ""),
            },
        }

    def inspect(
        self, context: Mapping[str, Any], command_id: str, value: Mapping[str, Any]
    ) -> dict[str, Any]:
        context = self._bound(context)
        if command_id == "fusion.nested_text.batch":
            conn = get_connection(require_project=True, require_timeline=True)
            observations = [
                self._inspect_nested_text_update(conn, context, {
                    "projectId": value["projectId"],
                    "timelineId": value["timelineId"],
                    "revision": value["revision"],
                    **dict(update),
                })
                for update in value["updates"]
            ]
            return {
                "targets": [
                    deepcopy(target)
                    for observation in observations
                    for target in observation["targets"]
                ],
                "preState": {"items": [
                    deepcopy(dict(observation["preState"]))
                    for observation in observations
                ]},
                "locator": {"items": [
                    deepcopy(dict(observation["locator"]))
                    for observation in observations
                ]},
            }
        if command_id in _OFFLINE_COMMANDS:
            state = deepcopy(dict(value))
            digest = _digest(state)
            return {
                "targets": [{"kind": "offline_coordinate", "stableId": f"coordinate_{digest.removeprefix('sha256:')}", "revision": digest}],
                "preState": state,
                "locator": {},
            }
        if command_id == "fusion.template.show":
            path = self._resolve_template_path(str(value["name"]))
            state = _path_state(path)
            return {
                "targets": [{"kind": "media", "stableId": f"template_{hashlib.sha256(str(path).encode()).hexdigest()}", "revision": state["digest"]}],
                "preState": state,
                "locator": {"templatePath": str(path)},
            }
        if command_id == "fusion.tool.registry":
            registry = self._read_tool_registry(value)
            state = {"registry": registry, "digest": _digest(registry)}
            return {
                "targets": [{"kind": "project_library", "stableId": "fusion_tool_registry", "revision": state["digest"]}],
                "preState": state, "locator": {},
            }
        if command_id == "lut.list":
            rows = self._scan_luts(value)
            state = {"rows": rows, "digest": _digest(rows)}
            return {
                "targets": [{"kind": "project_library", "stableId": "lut_registry_user_and_declared_roots", "revision": state["digest"]}],
                "preState": state,
                "locator": {},
            }
        if command_id in _ARTIFACT_READ_COMMANDS:
            artifact_id = str(value.get("artifactId") or value.get("templateArtifactId") or value.get("sourceArtifactId"))
            state = _artifact_state(context, artifact_id)
            return {
                "targets": [{"kind": "media", "stableId": artifact_id, "revision": state["digest"]}],
                "preState": state,
                "locator": {"artifactId": artifact_id},
            }
        if command_id == "fusion.image.batch":
            conn = get_connection(require_project=True, require_timeline=True)
            rows = []
            targets = []
            locators = []
            for requested in value["items"]:
                public_item_id = str(requested["timelineItemId"])
                index = int(requested["compositionIndex"])
                item, track_index, record_frame = _find_item(conn, context, public_item_id)
                comp = _composition(item, index)
                state = _comp_state(comp)
                state["name"] = _composition_name(item, index, comp.GetAttrs() or {})
                rows.append(state)
                target_id = f"{public_item_id}:fusion:{index}"
                targets.append({"kind": "fusion_composition", "stableId": target_id, "revision": state["digest"]})
                locators.append({"timelineItemId": public_item_id, "compositionIndex": index, "trackIndex": track_index, "recordFrame": record_frame, "clipName": str(item.GetName() or "")})
            return {
                "targets": targets,
                "preState": {"items": rows, "timelineProtected": self._timeline_state(conn)},
                "locator": {"items": locators},
            }
        if command_id in _FILESYSTEM_COMMANDS:
            paths = self._filesystem_targets(context, command_id, value)
            declared_parents = self._filesystem_parent_targets(command_id, paths)
            if any(
                (path.parent.exists() and (not path.parent.is_dir() or path.parent.is_symlink()))
                or (not path.parent.exists() and path.parent not in declared_parents)
                for path in paths
            ):
                raise InventoryValidationError(
                    "descriptor-bound filesystem target parent must already exist"
                )
            states = self._filesystem_states(command_id, paths)
            if command_id in {"fusion.template.uninstall", "lut.remove"} and any(
                state["kind"] == "absent" for state in states.values()
            ):
                raise InventoryValidationError("descriptor-bound filesystem removal target is absent")
            targets = [{
                "kind": "configuration" if artifact_id == "configuration_RESOLVE_TEMPLATE_DIR" else "media",
                "stableId": artifact_id,
                "revision": state["digest"],
            } for artifact_id, state in states.items()]
            locator = {}
            if command_id == "fusion.template.icon.set":
                locator["templatePath"] = str(self._resolve_template_path(str(value["template"])))
            return {"targets": targets, "preState": states, "locator": locator}

        conn = get_connection(require_project=True, require_timeline=command_id != "lut_refresh")
        if command_id == "fusion.nested_text.update":
            return self._inspect_nested_text_update(conn, context, value)
        if command_id == "lut_refresh":
            project_id = str(value["projectId"])
            revision = str(value["revision"])
            return {
                "targets": [{"kind": "project", "stableId": project_id, "revision": revision}],
                "preState": {"projectRevision": revision},
                "locator": {},
            }
        if command_id in {"fusion.insert_setting", "fusion.insert_settings.batch"}:
            timeline_id = str(value["timelineId"])
            revision = str(value["revision"])
            return {
                "targets": [{"kind": "timeline", "stableId": timeline_id, "revision": revision}],
                "preState": self._timeline_state(conn),
                "locator": {},
            }

        if command_id == "fusion.text.batch":
            rows: list[dict[str, Any]] = []
            states: dict[str, Any] = {}
            targets: list[dict[str, str]] = []
            for update in value["updates"]:
                public_item_id = str(update["timelineItemId"])
                item, track_index, record_frame = _find_item(conn, context, public_item_id)
                index = int(update["compositionIndex"])
                comp = _composition(item, index)
                state = _comp_state(comp)
                target_id = f"{public_item_id}:fusion:{index}"
                if target_id not in states:
                    states[target_id] = state
                    targets.append({"kind": "fusion_composition", "stableId": target_id, "revision": state["digest"]})
                rows.append({
                    "timelineItemId": public_item_id,
                    "compositionIndex": index,
                    "trackIndex": track_index,
                    "recordFrame": record_frame,
                    "clipName": str(item.GetName() or ""),
                })
            return {
                "targets": targets,
                "preState": {"compositions": states, "timeline": self._timeline_state(conn), "digest": _digest(states)},
                "locator": {"updates": rows},
            }

        public_item_id = str(value["timelineItemId"])
        item, track_index, record_frame = _find_item(conn, context, public_item_id)
        locator = {
            "timelineItemId": public_item_id,
            "trackIndex": track_index,
            "recordFrame": record_frame,
            "clipName": str(item.GetName() or ""),
        }
        if command_id == "dctl.apply":
            artifact_id = str(value["dctlArtifactId"])
            _artifact_state(context, artifact_id)
            node = int(value.get("nodeIndex", 1))
            getter = getattr(item, "GetLUT", None)
            before_lut = getter(node) if callable(getter) else None
            state = {"nodeIndex": node, "lut": before_lut}
            return {
                "targets": [{"kind": "clip", "stableId": public_item_id, "revision": str(value["revision"])}],
                "preState": state,
                "locator": locator,
            }

        index = int(value.get("compositionIndex", 1))
        comp = _composition(item, index)
        state = _comp_state(comp)
        state["name"] = _composition_name(item, index, comp.GetAttrs() or {})
        item_range = _timeline_item_range(item, record_frame)
        state["timelineItemRange"] = item_range
        locator["timelineItemRange"] = deepcopy(item_range)
        template_target = None
        if command_id == "fusion.template.apply":
            template_path = self._resolve_template_apply_path(str(value["template"]))
            template_state = _path_state(template_path)
            state["templateSource"] = template_state
            locator.update({
                "templatePath": str(template_path),
                "templateDigest": str(template_state["sha256"]),
            })
            template_target = {
                "kind": "media",
                "stableId": f"template_{hashlib.sha256(str(template_path).encode()).hexdigest()}",
                "revision": template_state["digest"],
            }
        if command_id == "fusion.comp.delete":
            count = int(item.GetFusionCompCount() or 0)
            names = []
            for current_index in range(1, count + 1):
                current = item.GetFusionCompByIndex(current_index)
                current_attrs = current.GetAttrs() if current else {}
                names.append(str((current_attrs or {}).get("COMPS_Name") or (current_attrs or {}).get("COMPN_Name") or ""))
            state.update({"compositionCount": count, "compositionNames": names})
        locator.update({"compositionIndex": index, "compositionName": state["name"]})
        target_id = f"{public_item_id}:fusion:{index}"
        targets = [{"kind": "fusion_composition", "stableId": target_id, "revision": state["digest"]}]
        if template_target is not None:
            targets.append(template_target)
        return {
            "targets": targets,
            "preState": state,
            "locator": locator,
        }

    def execute(
        self,
        context: Mapping[str, Any],
        command_id: str,
        value: Mapping[str, Any],
        prepared: Mapping[str, Any],
    ) -> dict[str, Any]:
        context = self._bound(context)
        execution_id = self._execution_id(context)
        before = deepcopy(dict(prepared["preState"]))
        checkpoint_id = None
        conn = None
        mutation_conn = None
        backups: dict[str, bytes | None] = {}
        created_directories: tuple[str, ...] = ()
        if command_id in _FILESYSTEM_COMMANDS:
            paths = self._filesystem_targets(context, command_id, value)
            for path in paths:
                backups[str(path)] = path.read_bytes() if path.is_file() else None
            created_directories = tuple(
                str(path) for path in self._filesystem_parent_targets(command_id, paths)
                if not path.exists()
            )
        elif command_id not in _READ_COMMANDS:
            conn = get_connection(require_project=True, require_timeline=command_id != "lut_refresh")
            mutation_conn = conn
            checkpoint = version_ops.create_checkpoint(
                conn,
                label=f"SDK Fusion recovery {execution_id}",
                kind="before_prompt",
                session_id=str(context.get("session", {}).get("sdkSessionId") or "sdk"),
            )
            checkpoint_id = str(checkpoint["id"])
        with self._checkpoint_lock:
            self._checkpoints[execution_id] = _ExecutionCheckpoint(
                checkpoint_id, backups, os.environ.get("RESOLVE_TEMPLATE_DIR"), created_directories
            )

        if command_id in _OFFLINE_COMMANDS:
            native = self._execute_coordinate(command_id, value)
        elif command_id == "fusion.template.show":
            path = Path(str(prepared["lowering"]["locator"]["templatePath"]))
            native = self._invoke_handler(context, command_id, value, prepared)
            native = {**dict(native), "name": value["name"], "artifactId": self._custody.adopt(context, str(path))}
        elif command_id == "fusion.tool.registry":
            native = self._read_tool_registry(value)
        elif command_id == "lut.list":
            native = {"luts": self._list_luts(context, value)}
        elif command_id == "fusion.tool.inputs":
            native = self._execute_tool_inputs(context, value)
        elif command_id == "fusion.keyframe.list":
            native = self._execute_keyframe_list(context, value)
        elif command_id in {"fusion.keyframe.add", "fusion.keyframe.set", "fusion.tool.set"}:
            native = self._execute_typed_tool_write(context, command_id, value)
        elif command_id == "fusion.nested_text.batch":
            native = self._execute_nested_text_batch(value, prepared, mutation_conn)
        elif command_id == "dctl.apply":
            native = self._execute_dctl(context, value)
        elif command_id == "lut_refresh":
            native = self._execute_lut_refresh()
        elif command_id == "fusion.image.batch":
            if conn is None:
                raise InventoryValidationError("Fusion image batch lost its prepared native connection")
            locators = prepared.get("lowering", {}).get("locator", {}).get("items", [])
            results = []
            batch_started = time.perf_counter()
            for index, requested in enumerate(value["items"]):
                item_started = time.perf_counter()
                try:
                    locator = locators[index]
                    item, _, _ = _find_item(conn, context, str(requested["timelineItemId"]))
                    position = requested.get("position") if isinstance(requested.get("position"), Mapping) else {}
                    zoom = requested.get("zoom") if isinstance(requested.get("zoom"), Mapping) else {}
                    native_row = fusion_image_ops.set_image_on_item(
                        conn, item, _managed_path(context, str(requested["imageArtifactId"])),
                        group_tool_name=requested.get("groupToolName"),
                        group_input_name=requested.get("groupInputName"),
                        import_media=bool(requested.get("importMedia", True)),
                        transform={"zoom_x": zoom.get("x"), "zoom_y": zoom.get("y"), "pan": position.get("x"), "tilt": position.get("y")},
                        composition_index=int(requested["compositionIndex"]),
                    )
                    if native_row.get("updated") is not True:
                        raise InventoryValidationError("Fusion image replacement produced no verified update")
                    results.append({"index": index, "ok": True, "durationMs": (time.perf_counter() - item_started) * 1_000, "result": native_row, "locator": deepcopy(dict(locator))})
                except Exception as exc:
                    results.append({"index": index, "ok": False, "durationMs": (time.perf_counter() - item_started) * 1_000, "error": {"code": type(exc).__name__, "message": str(exc)}})
            native = {"results": results, "durationMs": (time.perf_counter() - batch_started) * 1_000}
        elif command_id in {"fusion.comp.delete", "fusion.comp.rename"}:
            native = self._execute_comp_identity(context, command_id, value, prepared)
        elif command_id == "fusion.insert_settings.batch":
            lowerings = prepared.get("lowering", {}).get("itemLowerings")
            if not isinstance(lowerings, list) or len(lowerings) != len(value["items"]):
                raise InventoryValidationError("prepared Fusion setting insertion list is unavailable")
            common = {key: value[key] for key in ("projectId", "timelineId", "revision")}
            native = {
                "items": [
                    self._invoke_handler(
                        context,
                        "fusion.insert_setting",
                        {**common, **dict(item)},
                        {"lowering": {"locator": {}, **dict(lowering)}},
                    )
                    for item, lowering in zip(value["items"], lowerings)
                ]
            }
        else:
            native = self._invoke_handler(context, command_id, value, prepared)
        after = self.inspect_after(context, command_id, value, prepared)
        return {"nativeResult": native, "before": before, "after": after}

    def inspect_after(
        self,
        context: Mapping[str, Any],
        command_id: str,
        value: Mapping[str, Any],
        prepared: Mapping[str, Any],
    ) -> dict[str, Any]:
        context = self._bound(context)
        if command_id == "fusion.nested_text.batch":
            conn = get_connection(require_project=True, require_timeline=True)
            observations = [
                self._inspect_nested_text_update(conn, context, {
                    "projectId": value["projectId"],
                    "timelineId": value["timelineId"],
                    "revision": value["revision"],
                    **dict(update),
                })
                for update in value["updates"]
            ]
            return {"items": [
                deepcopy(dict(observation["preState"]))
                for observation in observations
            ]}
        if command_id in _ARTIFACT_READ_COMMANDS or command_id in {"fusion.template.show", "fusion.tool.registry", "lut.list"}:
            return self.inspect(context, command_id, value)["preState"]
        if command_id in _OFFLINE_COMMANDS:
            return self.inspect(context, command_id, value)["preState"]
        if command_id in _FILESYSTEM_COMMANDS:
            if command_id == "fusion.template.icon.set":
                template_path = prepared.get("lowering", {}).get("locator", {}).get("templatePath")
                if not isinstance(template_path, str) or not Path(template_path).is_absolute():
                    raise InventoryValidationError("prepared template icon target is unavailable")
                paths = (Path(template_path).with_suffix(".png"),)
            elif command_id == "lut.remove":
                name = prepared.get("lowering", {}).get("handlerKwargs", {}).get("name")
                paths = (sdk_tools._safe_child_path(
                    (sdk_tools._home_app_support() / "LUT").resolve(), name, label="name"
                ),) if isinstance(name, str) and name else self._filesystem_targets(
                    context, command_id, value, after=True
                )
            else:
                paths = self._filesystem_targets(context, command_id, value, after=True)
            return self._filesystem_states(command_id, paths)
        if command_id in {"fusion.insert_setting", "fusion.insert_settings.batch"}:
            conn = get_connection(require_project=True, require_timeline=True)
            # Precise setting insertion can close and reopen the project through
            # its scratch-DB placement route. Rebind before independent readback
            # so verification does not inspect the pre-reopen Timeline handle.
            conn.refresh()
            return self._timeline_state(conn)
        if command_id == "lut_refresh":
            return {"apiAcknowledged": True, "projectRevision": str(value["revision"])}
        if command_id == "dctl.apply":
            conn = get_connection(require_project=True, require_timeline=True)
            item, _, _ = _find_item(conn, context, str(value["timelineItemId"]))
            getter = getattr(item, "GetLUT", None)
            return {"nodeIndex": int(value.get("nodeIndex", 1)), "lut": getter(int(value.get("nodeIndex", 1))) if callable(getter) else None}
        if command_id == "fusion.comp.delete":
            conn = get_connection(require_project=True, require_timeline=True)
            item, _, _ = _find_item(conn, context, str(value["timelineItemId"]))
            count = int(item.GetFusionCompCount() or 0)
            names = []
            for index in range(1, count + 1):
                comp = item.GetFusionCompByIndex(index)
                attrs = comp.GetAttrs() if comp else {}
                names.append(str((attrs or {}).get("COMPS_Name") or (attrs or {}).get("COMPN_Name") or ""))
            return {"compositionCount": count, "compositionNames": names, "digest": _digest(names)}
        if command_id == "fusion.template.apply":
            template_path = prepared.get("lowering", {}).get("locator", {}).get("templatePath")
            if not isinstance(template_path, str) or not Path(template_path).is_absolute():
                raise InventoryValidationError("prepared Fusion template source is unavailable")
            value = {**dict(value), "template": template_path}
        observed = self.inspect(context, command_id, value)
        return deepcopy(dict(observed["preState"]))

    def verify(
        self,
        context: Mapping[str, Any],
        command_id: str,
        value: Mapping[str, Any],
        prepared: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        before = result["before"]
        after = result["after"]
        if command_id == "fusion.nested_text.batch":
            native_rows = result["nativeResult"].get("results", ())
            before_items = before.get("items", ())
            after_items = after.get("items", ())
            updates = value.get("updates", ())
            passed = (
                len(native_rows) == len(updates)
                and len(before_items) == len(native_rows)
                and len(after_items) == len(native_rows)
                and all(
                    self._verify_exact(
                        "fusion.nested_text.update", updates[index],
                        before_items[index], after_items[index], row,
                    ) if row.get("ok") else before_items[index] == after_items[index]
                    for index, row in enumerate(native_rows)
                )
            )
        else:
            passed = self._verify_exact(command_id, value, before, after, result["nativeResult"])
        copy_source_fields = {
            "fusion.template.assets.add": "assetArtifactId",
            "fusion.template.icon.set": "pngArtifactId",
            "fusion.template.install": "artifactId",
            "lut.install": "sourceArtifactId",
        }
        source_field = copy_source_fields.get(command_id)
        if passed and source_field is not None:
            source = _managed_record(context, str(value[source_field]))
            expected = source.get("sha256")
            copied_files = [
                state for key, state in after.items() if key.startswith("affected_")
            ]
            passed = (
                isinstance(expected, str)
                and len(copied_files) == 1
                and all(
                    state.get("kind") == "file"
                    and state.get("sha256") == expected.removeprefix("sha256:")
                    for state in copied_files
                )
            )
        if passed and command_id == "lut.generate.identity":
            try:
                paths = self._filesystem_targets(context, command_id, value, after=True)
                inspected = sdk_tools.inspect_lut(str(paths[0])) if len(paths) == 1 else {}
                size = int(value["cubeSize"])
                size_line = str(inspected.get("size_line") or "").split()
                passed = (
                    size_line == ["LUT_3D_SIZE", str(size)]
                    and inspected.get("entries") == size ** 3
                )
            except (KeyError, OSError, TypeError, ValueError):
                passed = False
        if passed and command_id in {
            "fusion.keyframe.add", "fusion.keyframe.set", "fusion.tool.set",
        } and value.get("sourcePosition"):
            passed = self._verify_timed_tool_value(context, value)
        evidence = []
        for modality in fusion_emitted_evidence(command_id):
            evidence.append({
                "modality": modality,
                "digest": _digest(
                    {"commandId": command_id, "native": result["nativeResult"], "after": after}
                    if modality == "readback"
                    else {"commandId": command_id, "after": after}
                ),
                "summary": (
                    "Native acknowledgement agrees with the exact post-state observation."
                    if modality == "readback"
                    else "The exact descriptor-bound target was independently read back."
                ),
            })
        verification = {
            "outcome": "passed" if passed else "failed",
            "evidence": evidence,
            "protectedStatePreserved": True if passed else False,
        }
        return verification

    def recover(
        self, context: Mapping[str, Any], command_id: str, value: Mapping[str, Any]
    ) -> dict[str, Any]:
        context = self._bound(context)
        if command_id in _READ_COMMANDS:
            self.finalize(context)
            return {"outcome": "not_needed", "attempted": False, "manualActionRequired": False}
        execution_id = str(context.get("executionId") or context.get("execution", {}).get("executionId") or "")
        with self._checkpoint_lock:
            checkpoint = self._checkpoints.get(execution_id)
        if checkpoint is None:
            return {"outcome": "manual_required", "attempted": True, "manualActionRequired": True}
        try:
            if command_id in _FILESYSTEM_COMMANDS:
                for raw_path, contents in checkpoint.filesystem_backup.items():
                    path = Path(raw_path)
                    if contents is None:
                        if path.exists() and path.is_file():
                            path.unlink()
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(contents)
                if command_id == "fusion.template.dir":
                    if checkpoint.template_dir_before is None:
                        os.environ.pop("RESOLVE_TEMPLATE_DIR", None)
                    else:
                        os.environ["RESOLVE_TEMPLATE_DIR"] = checkpoint.template_dir_before
                for raw_directory in reversed(checkpoint.created_directories):
                    directory = Path(raw_directory)
                    if directory.is_dir() and not directory.is_symlink():
                        directory.rmdir()
            elif checkpoint.checkpoint_id:
                conn = get_connection(require_project=True)
                version_ops.restore_checkpoint(
                    conn,
                    checkpoint.checkpoint_id,
                    session_id=str(context.get("session", {}).get("sdkSessionId") or "sdk"),
                )
            else:
                raise InventoryValidationError("Fusion recovery checkpoint is unavailable")
        except Exception:
            return {"outcome": "failed", "attempted": True, "manualActionRequired": True}
        with self._checkpoint_lock:
            self._private_results.pop(execution_id, None)
            self._checkpoints.pop(execution_id, None)
        return {"outcome": "succeeded", "attempted": True, "manualActionRequired": False}

    @staticmethod
    def _timeline_state(conn: Any) -> dict[str, Any]:
        rows = []
        count = int(conn.timeline.GetTrackCount("video") or 0)
        for track in range(1, count + 1):
            for item in conn.timeline.GetItemListInTrack("video", track) or []:
                native_id = sdk_live_inspection.documented_unique_id(item)
                if native_id:
                    start = int(item.GetStart())
                    end = int(item.GetEnd())
                    rows.append({
                        "nativeId": native_id,
                        "track": track,
                        "start": start,
                        "end": end,
                        "duration": end - start,
                        "name": str(item.GetName() or ""),
                    })
        return {"items": rows, "digest": _digest(rows)}

    @staticmethod
    def _destination_artifact_ids(command_id: str, value: Mapping[str, Any]) -> tuple[str, ...]:
        fields = {
            "fusion.generate": ("destinationArtifactId",),
            "fusion.template.package_drfx": ("destinationArtifactId",),
            "fusion.template.scaffold": ("destinationArtifactId",),
            "fusion.template.assets.add": ("templateArtifactId",),
            "fusion.template.dir": ("directoryArtifactId",),
        }.get(command_id, ())
        return tuple(str(value[field]) for field in fields if isinstance(value.get(field), str))

    @staticmethod
    def _filesystem_targets(
        context: Mapping[str, Any], command_id: str, value: Mapping[str, Any], *, after: bool = False
    ) -> tuple[Path, ...]:
        if command_id in {"fusion.generate", "fusion.template.package_drfx", "fusion.template.scaffold", "lut.generate.identity"}:
            return (Path(_managed_path(
                context, str(value["destinationArtifactId"]), existing=None if after else False,
                require_reservation=True,
            )),)
        if command_id == "lut.install":
            source = Path(_managed_path(context, str(value["sourceArtifactId"]), existing=True))
            root = sdk_tools._home_app_support() / "LUT"
            if value.get("userSubfolder"):
                root = sdk_tools._safe_child_path(root, str(value["userSubfolder"]), label="folder")
            return (root / source.name,)
        if command_id == "lut.remove":
            record = _managed_record(context, str(value["installedArtifactId"]))
            origin = record.get("originPath")
            if not isinstance(origin, str):
                requested = str(value["installedArtifactId"])
                candidates = [
                    row for row in FusionPreparedActionRuntime._scan_luts({"roots": ["user"]})
                    if FusionArtifactCustody.identify(context, row["path"], stable_namespace=True) == requested
                ]
                if len(candidates) != 1:
                    raise InventoryValidationError("installed LUT custody record has no exact native origin identity")
                origin = candidates[0]["path"]
            path = Path(origin).resolve()
            expected = record.get("sha256")
            if not after and (
                not path.is_file()
                or path.is_symlink()
                or not isinstance(expected, str)
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected.removeprefix("sha256:")
            ):
                raise InventoryValidationError("installed LUT origin no longer matches managed custody")
            user_root = (sdk_tools._home_app_support() / "LUT").resolve()
            try:
                path.relative_to(user_root)
            except ValueError as exc:
                raise InventoryValidationError("only user-installed LUTs can be removed") from exc
            return (path,)
        if command_id == "fusion.template.assets.add":
            template = Path(_managed_path(context, str(value["templateArtifactId"]), existing=True))
            source = Path(_managed_path(context, str(value["assetArtifactId"]), existing=True))
            return (template.with_suffix("") / "assets" / source.name,)
        if command_id == "fusion.template.install":
            source = Path(_managed_path(context, str(value["artifactId"]), existing=True))
            return (sdk_tools._fusion_template_root(str(value["kind"])) / source.name,)
        if command_id == "fusion.template.uninstall":
            root = sdk_tools._fusion_template_root(str(value["kind"]))
            target = sdk_tools._safe_child_path(root, str(value["name"]), label="name")
            if not target.exists() and not str(value["name"]).endswith(".setting"):
                target = sdk_tools._safe_child_path(root, f"{value['name']}.setting", label="name")
            return (target,)
        if command_id == "fusion.template.icon.set":
            template = FusionPreparedActionRuntime._resolve_template_path(str(value["template"]))
            return (template.with_suffix(".png"),)
        if command_id == "fusion.template.dir":
            return (Path(_managed_path(context, str(value["directoryArtifactId"]), existing=True)),)
        return ()

    @staticmethod
    def _filesystem_states(command_id: str, paths: tuple[Path, ...]) -> dict[str, Any]:
        states = {
            f"affected_{hashlib.sha256(str(path).encode()).hexdigest()}": _path_state(path)
            for path in paths
        }
        if command_id == "fusion.template.dir":
            current = os.environ.get("RESOLVE_TEMPLATE_DIR")
            states["configuration_RESOLVE_TEMPLATE_DIR"] = {
                "kind": "configuration",
                "value": current,
                "digest": _digest({"RESOLVE_TEMPLATE_DIR": current}),
            }
        for parent in FusionPreparedActionRuntime._filesystem_parent_targets(command_id, paths):
            states[f"parent_{hashlib.sha256(str(parent).encode()).hexdigest()}"] = _path_state(parent)
        return states

    @staticmethod
    def _filesystem_parent_targets(command_id: str, paths: tuple[Path, ...]) -> tuple[Path, ...]:
        if command_id not in {
            "fusion.template.assets.add", "fusion.template.install", "lut.install",
        } or len(paths) != 1:
            return ()
        if command_id == "fusion.template.assets.add":
            root = paths[0].parent.parent.parent.resolve()
        else:
            root = sdk_tools._home_app_support().resolve()
        if not root.is_dir() or root.is_symlink():
            raise InventoryValidationError("filesystem installation root is unavailable")
        parent = paths[0].parent.resolve(strict=False)
        try:
            parent.relative_to(root)
        except ValueError as exc:
            raise InventoryValidationError("filesystem install parent escaped its managed root") from exc
        rows = []
        current = parent
        while current != root:
            rows.append(current)
            current = current.parent
        return tuple(reversed(rows))

    @staticmethod
    def _resolve_template_path(template: str) -> Path:
        if Path(template).name != template or "/" in template or "\\" in template:
            raise InventoryValidationError("Fusion template name must not contain a path")
        from ..commands import fusion as fusion_commands

        for directory in fusion_commands._template_directories():
            path = Path(directory) / template
            if path.is_file() and not path.is_symlink():
                return path.resolve()
        raise InventoryValidationError("exact installed Fusion template is unavailable")

    @staticmethod
    def _resolve_template_apply_path(template: str) -> Path:
        from ..commands import fusion as fusion_commands

        path = Path(str(fusion_commands._resolve_template_setting_path(template))).resolve()
        if not path.is_file() or path.is_symlink():
            raise InventoryValidationError("exact Fusion template setting is unavailable")
        return path

    @staticmethod
    def _read_tool_registry(value: Mapping[str, Any]) -> dict[str, Any]:
        conn = get_connection(require_timeline=False)
        return fusion_api.get_fusion_api(conn).list_registered_tools(
            query=value.get("query"), category=value.get("category"), limit=value.get("limit", 1024)
        )

    def _list_luts(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> list[dict[str, str]]:
        return [
            {"name": row["name"], "artifactId": self._custody.adopt(context, row["path"], stable_namespace=True), "root": row["root"]}
            for row in self._scan_luts(value)
        ]

    @staticmethod
    def _scan_luts(value: Mapping[str, Any]) -> list[dict[str, str]]:
        roots = set(value.get("roots") or ["user"])
        native = sdk_tools.list_luts(bool(roots - {"user"}))
        user_root = (sdk_tools._home_app_support() / "LUT").resolve()
        system_root = (sdk_tools._system_app_support() / "LUT").resolve()
        sdk_root = (sdk_tools.DEVELOPER_ROOT / "LUT").resolve()
        result = []
        for row in native:
            path = Path(str(row["path"])).resolve()
            root_kind = "user" if path.is_relative_to(user_root) else "resolve_system" if path.is_relative_to(system_root) else "resolve_sdk" if path.is_relative_to(sdk_root) else None
            if root_kind is None or root_kind not in roots:
                continue
            result.append({"name": path.name, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "root": root_kind})
        return result

    @staticmethod
    def _result_artifact_ids(command_id: str, value: Mapping[str, Any]) -> tuple[str, ...]:
        explicit = FusionPreparedActionRuntime._destination_artifact_ids(command_id, value)
        if explicit:
            return explicit
        return tuple(str(item) for key, item in value.items() if key.endswith("ArtifactId") and isinstance(item, str))

    def _invoke_handler(
        self,
        context: Mapping[str, Any],
        command_id: str,
        value: Mapping[str, Any],
        prepared: Mapping[str, Any],
    ) -> Any:
        module, function_name = self._handler(command_id)
        if prepared.get("lowering", {}).get("handlerName") != function_name:
            raise InventoryValidationError("prepared handler identity no longer matches the command")
        handler = getattr(module, function_name)
        while hasattr(handler, "__wrapped__"):
            handler = handler.__wrapped__
        kwargs = prepared.get("lowering", {}).get("handlerKwargs")
        if not isinstance(kwargs, Mapping):
            raise InventoryValidationError("prepared handler lowering is unavailable")
        kwargs = deepcopy(dict(kwargs))
        temporary_batch_path: str | None = None
        if command_id == "fusion.text.batch":
            locator_rows = prepared.get("lowering", {}).get("locator", {}).get("updates")
            if not isinstance(locator_rows, list) or len(locator_rows) != len(value.get("updates", [])):
                raise InventoryValidationError("prepared Fusion text batch locators are unavailable")
            entries = []
            for update, locator in zip(value["updates"], locator_rows):
                entries.append({
                    "track": locator["trackIndex"],
                    "record_frame": locator["recordFrame"],
                    "composition_index": update["compositionIndex"],
                    "tool": update["toolName"],
                    "inputs": [update["inputName"]],
                    "text": update["text"],
                    "exact_target": True,
                })
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as stream:
                json.dump(entries, stream, ensure_ascii=False, separators=(",", ":"))
                temporary_batch_path = stream.name
            kwargs["batch"] = temporary_batch_path
        if command_id == "fusion.template.apply":
            locator = prepared.get("lowering", {}).get("locator", {})
            template_path = locator.get("templatePath")
            template_digest = locator.get("templateDigest")
            if (
                not isinstance(template_path, str)
                or not isinstance(template_digest, str)
                or not Path(template_path).is_file()
                or Path(template_path).is_symlink()
                or hashlib.sha256(Path(template_path).read_bytes()).hexdigest()
                != template_digest.removeprefix("sha256:")
            ):
                raise InventoryValidationError("prepared Fusion template content changed before execution")
        captured: list[Any] = []
        globals_ = handler.__globals__
        replacements = {
            "output": lambda data, **_options: captured.append(deepcopy(data)),
            "success": lambda message, **_options: captured.append({"message": str(message)}),
            "dry_run_message": lambda message, **_options: captured.append({"message": str(message)}),
            "is_dry_run": lambda: False,
            "enforce_mutation_policy": lambda *_args, **_kwargs: None,
            "require_force_for_machine_mode": lambda **_kwargs: None,
            "get_connection": lambda **_kwargs: get_connection(
                require_project=bool(_kwargs.get("require_project")),
                require_timeline=bool(_kwargs.get("require_timeline")),
            ),
        }
        old: dict[str, Any] = {}
        exact_api_getter = None
        if command_id in _GRAPH_COMMANDS:
            conn = get_connection(require_project=True, require_timeline=True)
            item, _, _ = _find_item(conn, context, str(value["timelineItemId"]))
            comp = _composition(item, int(value["compositionIndex"]))
            def exact_api_getter(_conn: Any) -> _ExactFusionAPI:
                return _ExactFusionAPI(_conn, comp)
        with _HANDLER_LOCK:
            try:
                for name, replacement in replacements.items():
                    if name in globals_:
                        old[name] = globals_[name]
                        globals_[name] = replacement
                fusion_module = globals_.get("fusion_api")
                old_fusion_getter = None
                if exact_api_getter is not None and fusion_module is not None:
                    old_fusion_getter = fusion_module.get_fusion_api
                    fusion_module.get_fusion_api = exact_api_getter
                handler(**kwargs)
            finally:
                if exact_api_getter is not None and globals_.get("fusion_api") is not None:
                    globals_["fusion_api"].get_fusion_api = old_fusion_getter
                for name, original in old.items():
                    globals_[name] = original
                if temporary_batch_path is not None:
                    Path(temporary_batch_path).unlink(missing_ok=True)
        native = captured[-1] if captured else {"completed": True}
        if isinstance(native, Mapping):
            native = deepcopy(dict(native))
            if command_id == "fusion.template.assets.list":
                native["assets"] = [
                    {**row, "artifactId": self._custody.adopt(context, str(row["path"]))}
                    for row in native.get("assets", []) if isinstance(row, Mapping)
                ]
            elif command_id in {
                "fusion.template.assets.add", "fusion.template.icon.set", "fusion.template.install",
                "lut.install",
            } and isinstance(native.get("destination"), str):
                native["artifactId"] = self._custody.adopt(
                    context, str(native["destination"]), stable_namespace=command_id == "lut.install"
                )
        return native

    @staticmethod
    def _handler(command_id: str) -> tuple[Any, str]:
        if command_id.startswith("fusion."):
            from ..commands import fusion as module
        elif command_id.startswith("lut."):
            from ..commands import lut as module
        else:
            raise InventoryValidationError(f"no reviewed Fusion packet handler for {command_id}")
        names = {
            "fusion.comp.current": "comp_current",
            "fusion.comp.range": "comp_range", "fusion.comp.render": "comp_render",
            "fusion.effect.blur": "effect_blur", "fusion.effect.color_correct": "effect_color_correct",
            "fusion.effect.glow": "effect_glow", "fusion.effect.sharpen": "effect_sharpen",
            "fusion.effect.transform": "effect_transform", "fusion.generate": "generate",
            "fusion.image.batch": "image_batch", "fusion.image.set": "image_set", "fusion.insert_setting": "insert_setting",
            "fusion.keyer.chroma": "keyer_chroma", "fusion.keyframe.add": "keyframe_add",
            "fusion.keyframe.clear": "keyframe_clear", "fusion.keyframe.delete": "keyframe_delete",
            "fusion.keyframe.set": "keyframe_set", "fusion.macro.apply": "macro_apply",
            "fusion.keyframe.list": "keyframe_list",
            "fusion.mask.ellipse": "mask_ellipse", "fusion.mask.polygon": "mask_polygon",
            "fusion.mask.rectangle": "mask_rectangle", "fusion.nested_text.batch": "nested_text_batch", "fusion.nested_text.update": "nested_text_update",
            "fusion.node.add": "node_add", "fusion.node.connect": "node_connect",
            "fusion.node.delete": "node_delete", "fusion.node.disconnect": "node_disconnect",
            "fusion.setting.inspect": "setting_inspect", "fusion.setting.summary": "setting_summary_command",
            "fusion.setting.validate": "setting_validate", "fusion.template.apply": "template_apply",
            "fusion.template.assets.add": "template_assets_add", "fusion.template.assets.list": "template_assets_list",
            "fusion.template.dir": "template_dir", "fusion.template.icon.set": "template_icon_set",
            "fusion.template.install": "template_install", "fusion.template.package_drfx": "template_package_drfx",
            "fusion.template.scaffold": "template_scaffold", "fusion.template.uninstall": "template_uninstall",
            "fusion.template.show": "template_show", "fusion.template.validate": "template_validate",
            "fusion.text.batch": "text_batch", "fusion.text.set": "text_set",
            "fusion.tool.active": "tool_active", "fusion.tool.add": "tool_add",
            "fusion.tool.attrs": "tool_attrs", "fusion.tool.connect": "tool_connect", "fusion.tool.delete": "tool_delete",
            "fusion.tool.disconnect": "tool_disconnect", "fusion.tool.paste": "tool_paste",
            "fusion.tool.get": "tool_get", "fusion.tool.inputs": "tool_inputs", "fusion.tool.list": "tool_list",
            "fusion.tool.outputs": "tool_outputs", "fusion.tool.set": "tool_set", "fusion.tracker.add": "tracker_add",
            "lut.convert": "convert", "lut.generate.identity": "generate_identity", "lut.inspect": "inspect",
            "lut.install": "install", "lut.remove": "remove", "lut.validate": "validate",
        }
        function_name = names.get(command_id)
        if function_name is None:
            raise InventoryValidationError(f"no reviewed handler mapping for {command_id}")
        return module, function_name

    def _handler_kwargs(
        self,
        context: Mapping[str, Any],
        command_id: str,
        value: Mapping[str, Any],
        prepared: Mapping[str, Any],
        handler: Any,
    ) -> dict[str, Any]:
        locator = prepared.get("lowering", {}).get("locator", {})
        def artifact(field: str, existing: bool | None = True) -> str:
            return _managed_path(context, str(value[field]), existing=existing)

        def point(field: str, default: Mapping[str, Any]) -> Mapping[str, Any]:
            candidate = value.get(field, default)
            return candidate if isinstance(candidate, Mapping) else default

        def record(field: str) -> str:
            return str(value[field]["value"]["value"])

        def source(field: str) -> int:
            return int(value[field]["value"]["value"])

        def timeline_selector() -> dict[str, Any]:
            track = locator.get("trackIndex")
            record_frame = locator.get("recordFrame")
            geometry_bound = track is not None and record_frame is not None
            return {
                "clip_name": None if geometry_bound else locator.get("clipName"),
                "track": track,
                "record_frame": str(record_frame) if record_frame is not None else None,
            }

        builders: dict[str, Any] = {
            "fusion.comp.current": lambda: {},
            "fusion.comp.render": lambda: {"wait": True},
            "fusion.tool.paste": lambda: {},
            "fusion.comp.range": lambda: _composition_range_lowering(value, locator),
            "fusion.effect.blur": lambda: {"strength": float(value.get("blurStrength", 5.0))},
            "fusion.effect.color_correct": lambda: {"gain_r": float(value.get("redGain", 1.0)), "gain_g": float(value.get("greenGain", 1.0)), "gain_b": float(value.get("blueGain", 1.0)), "gamma": float(value.get("gamma", 1.0)), "saturation": float(value.get("saturation", 1.0))},
            "fusion.effect.glow": lambda: {"intensity": float(value.get("intensity", 0.5))},
            "fusion.effect.sharpen": lambda: {"amount": float(value.get("amount", 0.5))},
            "fusion.effect.transform": lambda: {"zoom": float(value.get("zoom", 1.0)), "x": float(point("position", {"x": 0, "y": 0})["x"]), "y": float(point("position", {"x": 0, "y": 0})["y"]), "rotation": float(value.get("rotationDegrees", 0.0))},
            "fusion.keyer.chroma": lambda: {"color": str(value.get("keyColor", "green")), "threshold": float(value.get("threshold", 0.3))},
            "fusion.keyframe.add": lambda: {"tool_name": value["toolName"], "input_name": value["inputName"], "frame": source("sourcePosition"), "value": json.dumps(value["value"], ensure_ascii=False, separators=(",", ":"))},
            "fusion.keyframe.clear": lambda: {"tool_name": value["toolName"], "input_name": value["inputName"], "force": True},
            "fusion.keyframe.delete": lambda: {"tool_name": value["toolName"], "input_name": value["inputName"], "frame": source("sourcePosition")},
            "fusion.keyframe.set": lambda: {"tool_name": value["toolName"], "input_name": value["inputName"], "frame": source("sourcePosition"), "value": json.dumps(value["value"], ensure_ascii=False, separators=(",", ":"))},
            "fusion.keyframe.list": lambda: {"tool_name": value["toolName"], "input_name": value["inputName"]},
            "fusion.mask.ellipse": lambda: {"center": f"{point('center', {'x': .5, 'y': .5})['x']},{point('center', {'x': .5, 'y': .5})['y']}", "width": float(value.get("width", .5)), "height": float(value.get("height", .5)), "softness": float(value.get("softness", 0))},
            "fusion.mask.rectangle": lambda: {"center": f"{point('center', {'x': .5, 'y': .5})['x']},{point('center', {'x': .5, 'y': .5})['y']}", "width": float(value.get("width", .5)), "height": float(value.get("height", .5)), "softness": float(value.get("softness", 0))},
            "fusion.mask.polygon": lambda: {"points": ";".join(f"{row['x']},{row['y']}" for row in value["points"])},
            "fusion.node.add": lambda: {"tool_type": value["toolType"], "name": value.get("name"), "x": int(point("flowPosition", {"x": -32768, "y": -32768})["x"]), "y": int(point("flowPosition", {"x": -32768, "y": -32768})["y"])},
            "fusion.tool.add": lambda: {"tool_type": value["toolType"], "name": value.get("name"), "x": int(point("flowPosition", {"x": -32768, "y": -32768})["x"]), "y": int(point("flowPosition", {"x": -32768, "y": -32768})["y"])},
            "fusion.node.connect": lambda: {"src_tool": value["source"]["toolName"], "src_output": value["source"]["portName"], "dst_tool": value["destination"]["toolName"], "dst_input": value["destination"]["portName"]},
            "fusion.tool.connect": lambda: {"src_tool": value["source"]["toolName"], "src_output": value["source"]["portName"], "dst_tool": value["destination"]["toolName"], "dst_input": value["destination"]["portName"]},
            "fusion.node.delete": lambda: {"tool_name": value["toolName"], "force": True},
            "fusion.tool.delete": lambda: {"tool_name": value["toolName"], "force": True},
            "fusion.node.disconnect": lambda: {"tool_name": value["destination"]["toolName"], "input_name": value["destination"]["portName"]},
            "fusion.tool.disconnect": lambda: {"tool_name": value["destination"]["toolName"], "input_name": value["destination"]["portName"]},
            "fusion.tool.active": lambda: {"tool_name": value["toolName"]},
            "fusion.tool.set": lambda: {"tool_name": value["toolName"], "input_name": value["inputName"], "value": json.dumps(value["value"], separators=(",", ":")) if not isinstance(value["value"], str) else value["value"], "time": source("sourcePosition") if value.get("sourcePosition") else None},
            "fusion.tracker.add": lambda: {"pattern_center": f"{point('patternCenter', {'x': .5, 'y': .5})['x']},{point('patternCenter', {'x': .5, 'y': .5})['y']}"},
            "fusion.generate": lambda: {"template_path": artifact("templateArtifactId"), "text": value.get("text"), "image": artifact("imageArtifactId") if value.get("imageArtifactId") else None, "bold_style": value.get("boldStyle", "ExtraBold"), "output_path": artifact("destinationArtifactId", False)},
            "fusion.setting.inspect": lambda: {"path": artifact("artifactId")},
            "fusion.setting.summary": lambda: {"path": artifact("artifactId"), "connections": bool(value.get("includeConnections")), "animated": bool(value.get("includeAnimatedInputs"))},
            "fusion.setting.validate": lambda: {"path": artifact("artifactId"), "fail_on_warning": bool(value.get("failOnWarning")), "runtime": False},
            "fusion.template.assets.add": lambda: {"template": artifact("templateArtifactId"), "file": artifact("assetArtifactId"), "overwrite": bool(value.get("overwrite"))},
            "fusion.template.assets.list": lambda: {"template": artifact("templateArtifactId")},
            "fusion.template.dir": lambda: {"set_path": artifact("directoryArtifactId")},
            "fusion.template.icon.set": lambda: {"template": locator["templatePath"], "png": artifact("pngArtifactId"), "overwrite": bool(value.get("overwrite"))},
            "fusion.template.install": lambda: {"path": artifact("artifactId"), "kind": value["kind"], "overwrite": bool(value.get("overwrite"))},
            "fusion.template.package_drfx": lambda: {"path": artifact("templateArtifactId"), "output_file": artifact("destinationArtifactId", False), "overwrite": bool(value.get("overwrite"))},
            # The carrier has already created and identity-bound the empty output
            # reservation. Writing that exact inode is not a user overwrite.
            "fusion.template.scaffold": lambda: {"kind": value["kind"], "name": value["name"], "output_path": artifact("destinationArtifactId", False), "overwrite": True},
            "fusion.template.uninstall": lambda: {"name": value["name"], "kind": value["kind"]},
            "fusion.template.show": lambda: {"name": value["name"]},
            "fusion.template.validate": lambda: {"path": artifact("artifactId")},
            "lut.inspect": lambda: {"path": artifact("artifactId")},
            "lut.validate": lambda: {"path": artifact("artifactId")},
            "lut.convert": lambda: {"path": artifact("sourceArtifactId"), "fmt": value["targetFormat"]},
            # The carrier has already created and identity-bound the empty
            # destination reservation. Filling that exact inode is not a user
            # overwrite, even when the public input omits `overwrite`.
            "lut.generate.identity": lambda: {"size": int(value["cubeSize"]), "output_path": artifact("destinationArtifactId", False), "overwrite": True},
            "lut.install": lambda: {"path": artifact("sourceArtifactId"), "folder": value.get("userSubfolder"), "overwrite": bool(value.get("overwrite"))},
            "lut.remove": lambda: {"name": str(self._filesystem_targets(context, command_id, value)[0].relative_to((sdk_tools._home_app_support() / 'LUT').resolve()))},
            "fusion.image.set": lambda: {"image_path": artifact("imageArtifactId"), **timeline_selector(), "group_tool": value.get("groupToolName"), "group_input": value.get("groupInputName"), "import_media": bool(value.get("importMedia", True)), "zoom_x": point("zoom", {}).get("x"), "zoom_y": point("zoom", {}).get("y"), "pan": point("position", {}).get("x"), "tilt": point("position", {}).get("y")},
            "fusion.insert_setting": lambda: {"path": artifact("settingArtifactId"), "name": value.get("clipName"), "record_frame": int(value["recordPosition"]["value"]["value"]), "duration": f"{int(value['clipDuration']['value']['value'])}f", "track": value.get("videoTrackIndex"), "position_x": point("position", {}).get("x"), "position_y": point("position", {}).get("y"), "text": value.get("text"), "image": artifact("imageArtifactId") if value.get("imageArtifactId") else None, "style_markdown": bool(value.get("styleMarkdown", True)), "bold_style": value.get("boldStyle", "ExtraBold")},
            "fusion.macro.apply": lambda: {"macro": value["macroName"], "clip_name": locator.get("clipName")},
            "fusion.template.apply": lambda: {"template": locator["templatePath"], **timeline_selector()},
            "fusion.nested_text.update": lambda: {"header": value.get("header"), "body": value.get("body"), **timeline_selector(), "header_clip": value.get("headerClipName"), "body_clip": value.get("bodyClipName"), "header_uppercase": bool(value.get("headerUppercase")), "header_double_spaces": bool(value.get("headerDoubleSpaces")), "bold_style": value.get("boldStyle", "ExtraBold")},
            "fusion.text.set": lambda: {"text": value["text"], **timeline_selector(), "role": value.get("role"), "tool": value.get("toolName"), "tool_candidate": value.get("toolCandidates"), "input_name": value.get("inputNames"), "uppercase": bool(value.get("uppercase")), "double_spaces": bool(value.get("doubleSpaces")), "styled": bool(value.get("styled")), "bold_style": value.get("boldStyle", "ExtraBold"), "cls_tool": value.get("stylingToolCandidates")},
            "fusion.text.batch": lambda: {"batch": "prepared-at-execution"},
            "fusion.tool.attrs": lambda: {"tool_name": value["toolName"]},
            "fusion.tool.get": lambda: {"tool_name": value["toolName"], "input_name": value["inputName"], "time": source("sourcePosition")},
            "fusion.tool.inputs": lambda: {"tool_name": value["toolName"]},
            "fusion.tool.list": lambda: {"selected": bool(value.get("selectedOnly"))},
            "fusion.tool.outputs": lambda: {"tool_name": value["toolName"]},
        }
        builder = builders.get(command_id)
        mapping: dict[str, Any] = builder() if builder is not None else {}
        signature = inspect.signature(handler)
        return {
            name: mapping[name] if name in mapping else _materialized_default(parameter)
            for name, parameter in signature.parameters.items()
        }

    def _execute_comp_identity(
        self, context: Mapping[str, Any], command_id: str, value: Mapping[str, Any], prepared: Mapping[str, Any]
    ) -> dict[str, Any]:
        conn = get_connection(require_project=True, require_timeline=True)
        item, _, _ = _find_item(conn, context, str(value["timelineItemId"]))
        index = int(value["compositionIndex"])
        comp = _composition(item, index)
        attrs = comp.GetAttrs() or {}
        old_name = _composition_name(item, index, attrs)
        if command_id == "fusion.comp.delete":
            composition_names = [str(name) for name in (item.GetFusionCompNameList() or [])]
            alternate_name = next((name for name in composition_names if name != old_name), None)
            loader = getattr(item, "LoadFusionCompByName", None)
            if alternate_name is not None:
                if not callable(loader):
                    raise APICallFailed(
                        "DaVinci Resolve cannot activate the retained Fusion composition before deletion"
                    )
                if not loader(alternate_name):
                    raise APICallFailed("DaVinci Resolve rejected loading the retained Fusion composition")
            result = item.DeleteFusionCompByName(old_name)
        else:
            result = item.RenameFusionCompByName(old_name, str(value["newName"]))
        if result is False:
            raise APICallFailed("DaVinci Resolve rejected the exact Fusion composition mutation")
        return {"previousName": old_name, "currentName": value.get("newName"), "acknowledged": True}

    @staticmethod
    def _execute_tool_inputs(context: Mapping[str, Any], value: Mapping[str, Any]) -> list[dict[str, Any]]:
        conn = get_connection(require_project=True, require_timeline=True)
        item, _, _ = _find_item(conn, context, str(value["timelineItemId"]))
        api = _ExactFusionAPI(conn, _composition(item, int(value["compositionIndex"])))
        inputs = api.get_tool_inputs(str(value["toolName"]))
        return [
            {
                "name": str(row.get("name") or row.get("id") or "Input"),
                "id": str(row.get("id") or row.get("name") or "Input"),
                "value": _public_fusion_value(row.get("value")),
            }
            for row in inputs.values()
            if isinstance(row, Mapping)
        ]

    @staticmethod
    def _execute_keyframe_list(context: Mapping[str, Any], value: Mapping[str, Any]) -> list[dict[str, Any]]:
        conn = get_connection(require_project=True, require_timeline=True)
        item, _, _ = _find_item(conn, context, str(value["timelineItemId"]))
        api = _ExactFusionAPI(conn, _composition(item, int(value["compositionIndex"])))
        tool = api.find_tool(str(value["toolName"]))
        input_obj = api._find_input_by_id(tool, str(value["toolName"]), str(value["inputName"]))
        getter = getattr(input_obj, "GetKeyFrames", None)
        if not callable(getter):
            raise APICallFailed("Fusion input does not expose authoritative keyframe enumeration")
        keyframes = getter()
        if not keyframes:
            return []
        if not isinstance(keyframes, Mapping):
            raise APICallFailed("Fusion input returned invalid keyframe enumeration")
        rows = []
        for frame in keyframes.values():
            numeric_frame = int(frame) if float(frame) == int(frame) else float(frame)
            rows.append({
                "frame": numeric_frame,
                "value": tool.GetInput(str(value["inputName"]), numeric_frame),
            })
        return rows

    @staticmethod
    def _execute_typed_tool_write(
        context: Mapping[str, Any], command_id: str, value: Mapping[str, Any]
    ) -> dict[str, Any]:
        conn = get_connection(require_project=True, require_timeline=True)
        item, _, _ = _find_item(conn, context, str(value["timelineItemId"]))
        api = _ExactFusionAPI(conn, _composition(item, int(value["compositionIndex"])))
        tool_name = str(value["toolName"])
        input_name = str(value["inputName"])
        typed_value = deepcopy(value["value"])
        source_position = value.get("sourcePosition")
        frame = (
            int(source_position["value"]["value"])
            if isinstance(source_position, Mapping)
            else None
        )
        if command_id in {"fusion.keyframe.add", "fusion.keyframe.set"}:
            if frame is None or api.set_keyframe(tool_name, input_name, frame, typed_value) is False:
                raise APICallFailed("DaVinci Resolve rejected the exact typed Fusion keyframe write")
        elif api.set_tool_input(tool_name, input_name, typed_value, frame) is False:
            raise APICallFailed("DaVinci Resolve rejected the exact typed Fusion input write")
        return {
            "toolName": tool_name,
            "inputName": input_name,
            "frame": frame,
            "value": typed_value,
            "acknowledged": True,
        }

    @staticmethod
    def _verify_timed_tool_value(context: Mapping[str, Any], value: Mapping[str, Any]) -> bool:
        try:
            conn = get_connection(require_project=True, require_timeline=True)
            item, _, _ = _find_item(conn, context, str(value["timelineItemId"]))
            api = _ExactFusionAPI(conn, _composition(item, int(value["compositionIndex"])))
            tool = api.find_tool(str(value["toolName"]))
            input_name = str(value["inputName"])
            input_obj = api._find_input_by_id(tool, str(value["toolName"]), input_name)
            getter = getattr(input_obj, "GetKeyFrames", None)
            if not callable(getter):
                return False
            keyframes = getter()
            if not isinstance(keyframes, Mapping):
                return False
            frame = value["sourcePosition"]["value"]["value"]
            if keyframes and float(frame) not in {float(candidate) for candidate in keyframes.values()}:
                return False
            return _native_values_equal(tool.GetInput(input_name, frame), value["value"])
        except (APICallFailed, KeyError, TypeError, ValueError):
            return False

    def _execute_dctl(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        conn = get_connection(require_project=True, require_timeline=True)
        item, _, _ = _find_item(conn, context, str(value["timelineItemId"]))
        node = int(value.get("nodeIndex", 1))
        path = _managed_path(context, str(value["dctlArtifactId"]), existing=True)
        setter = getattr(item, "SetLUT", None)
        getter = getattr(item, "GetLUT", None)
        if not callable(setter) or not callable(getter) or setter(node, path) is False:
            raise APICallFailed("DaVinci Resolve rejected the exact DCTL target")
        readback = getter(node)
        if (
            not isinstance(readback, str)
            or not Path(readback).is_absolute()
            or Path(readback).resolve() != Path(path).resolve()
        ):
            raise APICallFailed("DCTL readback does not match the managed artifact")
        return {
            "nodeIndex": node,
            "readbackName": Path(readback).name,
            "readbackPath": str(Path(readback).resolve()),
            "acknowledged": True,
        }

    @staticmethod
    def _execute_nested_text_batch(
        value: Mapping[str, Any], prepared: Mapping[str, Any], conn: Any
    ) -> dict[str, Any]:
        if conn is None:
            raise InventoryValidationError("Nested Fusion text batch has no live timeline connection")
        locators = prepared.get("lowering", {}).get("locator", {}).get("items")
        if not isinstance(locators, list) or len(locators) != len(value["updates"]):
            raise InventoryValidationError("Nested Fusion text batch locator binding is incomplete")
        entries = []
        for update, locator in zip(value["updates"], locators):
            if not isinstance(locator, Mapping):
                raise InventoryValidationError("Nested Fusion text batch locator is invalid")
            entries.append({
                "clip": None,
                "track": locator.get("trackIndex"),
                "record_frame": locator.get("recordFrame"),
                "header": update.get("header"),
                "body": update.get("body"),
                "header_clip": update.get("headerClipName"),
                "body_clip": update.get("bodyClipName"),
                "header_uppercase": bool(update.get("headerUppercase")),
                "header_double_spaces": bool(update.get("headerDoubleSpaces")),
                "bold_style": update.get("boldStyle", "ExtraBold"),
            })
        from ..commands import fusion as fusion_commands

        return fusion_commands._run_nested_text_batch(conn, entries, dry_run=False)

    @staticmethod
    def _execute_lut_refresh() -> dict[str, Any]:
        conn = get_connection(require_project=True)
        refresher = getattr(conn.project, "RefreshLUTList", None)
        if not callable(refresher):
            raise APICallFailed("RefreshLUTList is unavailable")
        result = refresher()
        if result is False:
            raise APICallFailed("RefreshLUTList returned False")
        return {"apiAcknowledged": True}

    @staticmethod
    def _execute_coordinate(command_id: str, value: Mapping[str, Any]) -> dict[str, Any]:
        if command_id == "fusion.setting.center_to_polypath":
            center = value["center"]
            return {"center": deepcopy(center), "polyPathPoint": {"x": center["x"] - 0.5, "y": center["y"] - 0.5}}
        point = value["polyPathPoint"]
        return {"polyPathPoint": deepcopy(point), "center": {"x": point["x"] + 0.5, "y": point["y"] + 0.5}}

    @staticmethod
    def _verify_exact(
        command_id: str, value: Mapping[str, Any], before: Mapping[str, Any], after: Mapping[str, Any], native: Any
    ) -> bool:
        if command_id == "fusion.image.batch":
            before_items = before.get("items") if isinstance(before.get("items"), list) else []
            after_items = after.get("items") if isinstance(after.get("items"), list) else []
            native_rows = native.get("results") if isinstance(native, Mapping) and isinstance(native.get("results"), list) else []
            return (
                before.get("timelineProtected") == after.get("timelineProtected")
                and len(before_items) == len(after_items) == len(native_rows) == len(value["items"])
                and all(isinstance(row, Mapping) for row in native_rows)
                and all(
                (row.get("ok") is True and before_items[index] != after_items[index])
                or (row.get("ok") is False and before_items[index] == after_items[index])
                for index, row in enumerate(native_rows)
                )
            )
        if command_id in _ARTIFACT_READ_COMMANDS:
            return before == after
        if command_id in _OFFLINE_COMMANDS:
            return before == after and isinstance(native, Mapping)
        if command_id in _READ_COMMANDS:
            return before == after and isinstance(native, (Mapping, list))
        if command_id in _FILESYSTEM_COMMANDS:
            if command_id in {"fusion.template.uninstall", "lut.remove"}:
                before_states = [state for key, state in before.items() if key != "__cutagentNativeTargets"]
                after_states = [state for key, state in after.items() if key != "__cutagentNativeTargets"]
                return (
                    bool(after_states)
                    and all(isinstance(state, Mapping) and state.get("kind") != "absent" for state in before_states)
                    and all(isinstance(state, Mapping) and state.get("kind") == "absent" for state in after_states)
                )
            if command_id == "fusion.template.dir":
                directory_states = [
                    state for key, state in after.items()
                    if key != "configuration_RESOLVE_TEMPLATE_DIR"
                ]
                configuration = after.get("configuration_RESOLVE_TEMPLATE_DIR", {})
                return (
                    bool(directory_states)
                    and all(state.get("kind") == "directory" for state in directory_states)
                    and isinstance(native, Mapping)
                    and configuration.get("value") == native.get("directory")
                )
            unchanged_idempotent_overwrite = (
                command_id in {"lut.generate.identity", "lut.install"}
                and value.get("overwrite") is True
                and before == after
            )
            return (
                bool(after)
                and (before != after or unchanged_idempotent_overwrite)
                and all(state.get("kind") != "absent" for state in after.values())
            )
        if command_id == "lut_refresh":
            return after.get("apiAcknowledged") is True
        if command_id == "fusion.text.batch":
            native_results = native.get("results") if isinstance(native, Mapping) else None
            if (
                not isinstance(native_results, list)
                or native.get("failure_count") != 0
                or len(native_results) != len(value["updates"])
                or before.get("timeline") != after.get("timeline")
            ):
                return False
            before_states = before.get("compositions")
            after_states = after.get("compositions")
            if not isinstance(before_states, Mapping) or not isinstance(after_states, Mapping):
                return False
            protected_before = deepcopy(dict(before_states))
            protected_after = deepcopy(dict(after_states))
            for update, native_row in zip(value["updates"], native_results):
                if not isinstance(native_row, Mapping) or native_row.get("ok") is not True or native_row.get("verified") is not True:
                    return False
                if native_row.get("tool_selected") != update["toolName"] or native_row.get("input_applied") != update["inputName"]:
                    return False
                target_id = f"{update['timelineItemId']}:fusion:{int(update['compositionIndex'])}"
                after_row = _input_row(after_states.get(target_id, {}), update["toolName"], update["inputName"])
                if not isinstance(after_row, Mapping) or not _native_values_equal(after_row.get("value"), update["text"]):
                    return False
                for states in (protected_before, protected_after):
                    state = states.get(target_id)
                    row = _input_row(state, update["toolName"], update["inputName"]) if isinstance(state, Mapping) else None
                    if isinstance(row, dict):
                        row["value"] = "__cutagent_requested_text__"
                    if isinstance(state, dict):
                        for key in ("digest", "protectedDigest", "renameProtectedDigest"):
                            state.pop(key, None)
            return protected_before == protected_after
        if command_id == "dctl.apply":
            return (
                isinstance(after.get("lut"), str)
                and Path(str(after["lut"])).is_absolute()
                and isinstance(native, Mapping)
                and isinstance(native.get("readbackPath"), str)
                and Path(str(after["lut"])).resolve() == Path(str(native["readbackPath"])).resolve()
            )
        if command_id == "fusion.comp.delete":
            return (
                after.get("compositionCount") == before.get("compositionCount", 0) - 1
                and before.get("name") not in set(after.get("compositionNames", ()))
            )
        if command_id == "fusion.comp.rename":
            return (
                after.get("name") == value["newName"]
                and before.get("name") != after.get("name")
                and isinstance(before.get("renameProtectedDigest"), str)
                and after.get("renameProtectedDigest") == before.get("renameProtectedDigest")
            )
        if command_id == "fusion.comp.range":
            item_range = before.get("timelineItemRange")
            after_range = after.get("timelineItemRange")
            record_start = item_range.get("recordStart") if isinstance(item_range, Mapping) else None
            return (
                isinstance(record_start, int)
                and not isinstance(record_start, bool)
                and after_range == item_range
                and isinstance(before.get("protectedDigest"), str)
                and after.get("protectedDigest") == before.get("protectedDigest")
                and after.get("renderStart") == value["range"]["start"] - record_start
                and after.get("renderEnd") == value["range"]["endExclusive"] - record_start - 1
            )
        if command_id == "fusion.tool.active":
            return after.get("activeTool") == value["toolName"]
        if command_id in {"fusion.node.delete", "fusion.tool.delete"}:
            return value["toolName"] in _node_map(before) and value["toolName"] not in _node_map(after)
        if command_id in {"fusion.node.connect", "fusion.tool.connect"}:
            row = _input_row(after, value["destination"]["toolName"], value["destination"]["portName"])
            connection = row.get("connection") if isinstance(row, Mapping) else None
            before_protected = _connection_protected_digest(
                before, value["destination"]["toolName"], value["destination"]["portName"]
            )
            after_protected = _connection_protected_digest(
                after, value["destination"]["toolName"], value["destination"]["portName"]
            )
            return (
                isinstance(connection, Mapping)
                and connection.get("node") == value["source"]["toolName"]
                and connection.get("port") == value["source"]["portName"]
                and before_protected is not None
                and after_protected == before_protected
            )
        if command_id in {"fusion.node.disconnect", "fusion.tool.disconnect"}:
            row = _input_row(after, value["destination"]["toolName"], value["destination"]["portName"])
            before_protected = _connection_protected_digest(
                before, value["destination"]["toolName"], value["destination"]["portName"]
            )
            after_protected = _connection_protected_digest(
                after, value["destination"]["toolName"], value["destination"]["portName"]
            )
            return (
                isinstance(row, Mapping)
                and row.get("connection") is None
                and before_protected is not None
                and after_protected == before_protected
            )
        if command_id == "fusion.tool.set":
            row = _input_row(after, value["toolName"], value["inputName"])
            if not isinstance(row, Mapping):
                return False
            if value.get("sourcePosition"):
                return bool(row.get("keyframes")) or (
                    row.get("connection") is None
                    and row.get("expression") in (None, "")
                    and _native_values_equal(row.get("value"), value["value"])
                )
            return _native_values_equal(row.get("value"), value["value"])
        if command_id in {"fusion.keyframe.add", "fusion.keyframe.set"}:
            row = _input_row(after, value["toolName"], value["inputName"])
            return isinstance(row, Mapping) and bool(row.get("keyframes"))
        if command_id == "fusion.keyframe.delete":
            row = _input_row(after, value["toolName"], value["inputName"])
            before_row = _input_row(before, value["toolName"], value["inputName"])
            if not isinstance(row, Mapping) or not isinstance(before_row, Mapping):
                return False
            target = float(value["sourcePosition"]["value"]["value"])
            try:
                before_frames = sorted(float(frame) for frame in (before_row.get("keyframes") or {}).values())
                after_frames = sorted(float(frame) for frame in (row.get("keyframes") or {}).values())
            except (AttributeError, TypeError, ValueError):
                return False
            expected = [frame for frame in before_frames if not math.isclose(frame, target, abs_tol=1e-6)]
            return (
                len(expected) == len(before_frames) - 1
                and len(after_frames) == len(expected)
                and all(math.isclose(left, right, abs_tol=1e-6) for left, right in zip(after_frames, expected))
            )
        if command_id == "fusion.keyframe.clear":
            row = _input_row(after, value["toolName"], value["inputName"])
            return (
                isinstance(row, Mapping)
                and not row.get("keyframes")
                and row.get("connection") is None
                and row.get("expression") in (None, "")
            )
        if command_id in {"fusion.node.add", "fusion.tool.add"}:
            added = set(_node_map(after)) - set(_node_map(before))
            if len(added) != 1:
                return False
            node = _node_map(after)[next(iter(added))]
            if node.get("type") != value["toolType"] or (value.get("name") is not None and node.get("name") != value["name"]):
                return False
            requested = value.get("flowPosition")
            return requested is None or _native_values_equal(node.get("flowPosition"), requested)
        if command_id in _CREATE_TOOL_TYPES:
            return _verify_created_tool(command_id, value, before, after)
        if command_id in {"fusion.insert_setting", "fusion.insert_settings.batch"}:
            before_ids = {row.get("nativeId") for row in before.get("items", ())}
            added = [row for row in after.get("items", ()) if row.get("nativeId") not in before_ids]
            requested = [value] if command_id == "fusion.insert_setting" else list(value["items"])
            if len(added) != len(requested):
                return False
            preserved = {
                row.get("nativeId"): row for row in after.get("items", ())
                if row.get("nativeId") in before_ids
            }
            if any(preserved.get(row.get("nativeId")) != row for row in before.get("items", ())):
                return False
            remaining = list(added)
            for item in requested:
                requested_track = item.get("videoTrackIndex")
                matches = [row for row in remaining if (
                    row.get("start") == int(item["recordPosition"]["value"]["value"])
                    and row.get("duration") == int(item["clipDuration"]["value"]["value"])
                    and (requested_track is None or row.get("track") == int(requested_track))
                    and (item.get("clipName") is None or row.get("name") == item.get("clipName"))
                )]
                if len(matches) != 1:
                    return False
                remaining.remove(matches[0])
            return not remaining
        if command_id == "fusion.comp.render":
            return isinstance(native, Mapping) and after.get("rendering") is False
        if command_id == "fusion.tool.paste":
            return bool(set(_node_map(after)) - set(_node_map(before)))
        if command_id in _LIVE_HANDLER_COMMANDS:
            return before.get("digest") != after.get("digest") and isinstance(native, Mapping)
        return before != after and isinstance(native, Mapping)
