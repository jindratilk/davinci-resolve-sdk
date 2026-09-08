"""Private exact-target Fusion graph lowering for the authenticated SDK runtime."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from importlib.resources import files
from typing import Any

from ..errors import APICallFailed, SdkMutationStaleRevision, ValidationError
from . import timeline_ops
from .sdk_live_inspection import (
    _fusion_graph_evidence,
    documented_unique_id,
    fusion_graph_digest,
    inspect_fusion_compositions,
)


def _sha256(value: Any) -> str:
    return fusion_graph_digest(value)


def _assert_expected_graph_digest(native_graph_evidence: Any, expected_digest: Any) -> None:
    if not isinstance(expected_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest) is None:
        raise ValidationError("The exact Fusion composition digest precondition is malformed.")
    if _sha256(native_graph_evidence) != expected_digest:
        raise SdkMutationStaleRevision("The exact Fusion composition digest precondition is stale.")


def _assert_locked_graph_precondition(comp: Any, observed_graph: Any, expected_digest: Any) -> None:
    locked_graph = _fusion_graph_evidence(comp, None)
    if locked_graph != observed_graph:
        raise SdkMutationStaleRevision("The exact Fusion composition changed before the undo transaction.")
    _assert_expected_graph_digest(locked_graph, expected_digest)


def _registry() -> dict[str, Any]:
    path = files("cutagent_cli.public_reference").joinpath("fusion-registry.json")
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise APICallFailed("The packaged Fusion registry is unavailable.") from exc
    status = registry.get("releaseStatus")
    if status != "verified":
        raise APICallFailed(
            "The Fusion graph runtime is not activated for this registry.",
            details={"release_status": status},
        )
    return registry


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(float(value)) != float("inf")


def _validate_value(port: dict[str, Any], value: Any) -> None:
    data_type = port.get("dataType")
    valid = (
        (data_type == "Number" and _finite_number(value))
        or (data_type in {"Text", "String"} and isinstance(value, str) and len(value) <= 65_536)
        or (data_type == "Boolean" and isinstance(value, bool))
        or (data_type in {"Point", "Point2D"} and isinstance(value, list) and len(value) == 2 and all(_finite_number(item) for item in value))
        or (data_type == "Point3D" and isinstance(value, list) and len(value) == 3 and all(_finite_number(item) for item in value))
        or (data_type == "Color" and isinstance(value, list) and len(value) == 4 and all(_finite_number(item) for item in value))
    )
    if not valid:
        raise ValidationError("Fusion graph input value does not match the packaged registry data type.")
    if data_type != "Number":
        return
    observed = port.get("observed") if isinstance(port.get("observed"), dict) else {}
    minimum = observed.get("minAllowed")
    maximum = observed.get("maxAllowed")
    if _finite_number(minimum) and value < minimum:
        raise ValidationError("Fusion graph input value is below the packaged registry minimum.")
    if _finite_number(maximum) and value > maximum:
        raise ValidationError("Fusion graph input value is above the packaged registry maximum.")
    enum_values = next((item for key, item in observed.items() if key.startswith("INPST_ComboControl_ID") and isinstance(item, dict)), None)
    if enum_values is not None and str(value) not in enum_values:
        raise ValidationError("Fusion graph input value is absent from the packaged registry enum.")


def _validate_graph(request: Any, registry: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict) or set(request) != {"schema", "schemaVersion", "registryDigest", "graph"}:
        raise ValidationError("Fusion graph request must use the closed semantic contract.")
    if request.get("schema") != "cutagent.fusion.graph-request" or request.get("schemaVersion") != 1:
        raise ValidationError("Fusion graph request version is unsupported.")
    if request.get("registryDigest") != registry.get("registryDigest"):
        raise ValidationError("Fusion graph registry digest does not match the packaged runtime registry.")
    graph = request.get("graph")
    if not isinstance(graph, dict) or set(graph) != {"nodes", "connections", "animations", "outputs"}:
        raise ValidationError("Fusion graph payload must use the closed semantic contract.")
    nodes = graph.get("nodes")
    connections = graph.get("connections")
    animations = graph.get("animations")
    outputs = graph.get("outputs")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 1_024:
        raise ValidationError("Fusion graph node count is invalid.")
    if not isinstance(connections, list) or len(connections) > 4_096:
        raise ValidationError("Fusion graph connection count is invalid.")
    if not isinstance(animations, list) or len(animations) > 10_000:
        raise ValidationError("Fusion graph animation count is invalid.")
    if not isinstance(outputs, list) or not 1 <= len(outputs) <= 64:
        raise ValidationError("Fusion graph outputs are invalid.")
    definitions = {row["id"]: row for row in registry.get("nodes", [])}
    node_ids: set[str] = set()
    node_types: dict[str, str] = {}
    node_rows: dict[str, dict[str, Any]] = {}
    for row in nodes:
        if not isinstance(row, dict) or set(row) != {"id", "type", "inputs"}:
            raise ValidationError("Fusion graph node is malformed.")
        node_id = row.get("id")
        node_type = row.get("type")
        if not isinstance(node_id, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", node_id) is None or node_id in node_ids or node_type not in definitions:
            raise ValidationError("Fusion graph node identity or type is invalid.")
        if not isinstance(row.get("inputs"), dict):
            raise ValidationError("Fusion graph node inputs are invalid.")
        allowed_inputs = {port["id"]: port for port in definitions[node_type].get("inputs", [])}
        for key, value in row["inputs"].items():
            if key not in allowed_inputs:
                raise ValidationError("Fusion graph contains an input absent from the packaged registry.")
            _validate_value(allowed_inputs[key], value)
        node_ids.add(node_id)
        node_types[node_id] = node_type
        node_rows[node_id] = row
    verified = {
        (row["source"]["node"], row["source"]["port"], row["target"]["node"], row["target"]["port"])
        for row in registry.get("connections", [])
    }
    occupied: set[tuple[str, str]] = set()
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for row in connections:
        if not isinstance(row, dict) or set(row) != {"source", "target"}:
            raise ValidationError("Fusion graph connection is malformed.")
        try:
            if set(row["source"]) != {"node", "port"} or set(row["target"]) != {"node", "port"}:
                raise KeyError("closed endpoint")
            source_node, source_port = row["source"]["node"], row["source"]["port"]
            target_node, target_port = row["target"]["node"], row["target"]["port"]
        except (KeyError, TypeError) as exc:
            raise ValidationError("Fusion graph connection is malformed.") from exc
        if source_node not in node_types or target_node not in node_types:
            raise ValidationError("Fusion graph connection references an unknown node.")
        if (node_types[source_node], source_port, node_types[target_node], target_port) not in verified:
            raise ValidationError("Fusion graph connection was not verified by the packaged registry.")
        if (target_node, target_port) in occupied:
            raise ValidationError("Fusion graph input has more than one source.")
        occupied.add((target_node, target_port))
        outgoing[source_node].add(target_node)
    for node_id, node_type in node_types.items():
        for port in definitions[node_type].get("inputs", []):
            if port.get("required") is True and port["id"] not in node_rows[node_id]["inputs"] and (node_id, port["id"]) not in occupied:
                raise ValidationError("Fusion graph required input is not supplied.")
    if len(set(outputs)) != len(outputs) or any(output not in node_ids or node_types[output] != "MediaOut" for output in outputs):
        raise ValidationError("Fusion graph output must reference a MediaOut node.")
    animated_inputs: set[tuple[str, str]] = set()
    for row in animations:
        if not isinstance(row, dict) or set(row) != {"node", "input", "animation"} or row.get("node") not in node_ids or not isinstance(row.get("input"), str):
            raise ValidationError("Fusion graph animation target is invalid.")
        allowed_inputs = {port["id"]: port for port in definitions[node_types[row["node"]]].get("inputs", [])}
        if row["input"] not in allowed_inputs:
            raise ValidationError("Fusion graph animation input is absent from the packaged registry.")
        port = allowed_inputs[row["input"]]
        if not isinstance(port.get("observed"), dict) or port["observed"].get("animatable") is not True:
            raise ValidationError("Fusion graph input is not registry-observed as animatable.")
        animation_key = (row["node"], row["input"])
        if animation_key in animated_inputs:
            raise ValidationError("Fusion graph input has more than one animation.")
        animated_inputs.add(animation_key)
        animation = row.get("animation")
        if not isinstance(animation, dict) or animation.get("kind") != "keyframes":
            raise ValidationError("Fusion graph animation is invalid.")
        if set(animation) != {"kind", "keyframes"} or not isinstance(animation.get("keyframes"), list):
            raise ValidationError("Fusion graph keyframe animation is invalid.")
        if not 1 <= len(animation["keyframes"]) <= 10_000:
            raise ValidationError("Fusion graph keyframe count is invalid.")
        previous_time: int | None = None
        for keyframe in animation["keyframes"]:
            if (not isinstance(keyframe, dict) or set(keyframe) != {"time", "value"}
                    or not isinstance(keyframe.get("time"), int) or isinstance(keyframe.get("time"), bool)
                    or (previous_time is not None and keyframe["time"] <= previous_time)):
                raise ValidationError("Fusion graph keyframe is invalid.")
            _validate_value(port, keyframe["value"])
            previous_time = keyframe["time"]
    visited: set[str] = set()
    active: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in active:
            raise ValidationError("Fusion graph contains a cycle.")
        if node_id in visited:
            return
        active.add(node_id)
        for next_id in outgoing[node_id]:
            visit(next_id)
        active.remove(node_id)
        visited.add(node_id)

    for node_id in node_ids:
        visit(node_id)
    output_ids = set(outputs)

    def reaches_output(node_id: str, seen: set[str]) -> bool:
        if node_id in output_ids:
            return True
        if node_id in seen:
            return False
        return any(reaches_output(next_id, seen | {node_id}) for next_id in outgoing[node_id])

    if any(not reaches_output(node_id, set()) for node_id in node_ids):
        raise ValidationError("Fusion graph node has no path to an output.")
    return request


def _exact_target(conn: Any, target: dict[str, Any]) -> tuple[Any, Any]:
    project_id = documented_unique_id(getattr(conn, "project", None))
    timeline_id = documented_unique_id(getattr(conn, "timeline", None))
    if project_id != target.get("projectNativeId") or timeline_id != target.get("timelineNativeId"):
        raise SdkMutationStaleRevision("The exact Fusion project or timeline target is stale.")
    matches = []
    track_count = int(conn.timeline.GetTrackCount("video") or 0)
    for track_index in range(1, track_count + 1):
        for item in conn.timeline.GetItemListInTrack("video", track_index) or []:
            if documented_unique_id(item) == target.get("timelineItemNativeId"):
                matches.append(item)
    if len(matches) != 1:
        raise SdkMutationStaleRevision("The exact Fusion timeline-item target is missing or ambiguous.")
    item = matches[0]
    index = target.get("compositionIndex")
    if not isinstance(index, int) or isinstance(index, bool) or index < 1 or index > 128:
        raise ValidationError("The exact Fusion composition index is invalid.")
    comp = item.GetFusionCompByIndex(index)
    if comp is None:
        raise SdkMutationStaleRevision("The exact Fusion composition target no longer exists.")
    attrs = comp.GetAttrs() or {}
    name = str(attrs.get("COMPS_Name") or attrs.get("COMPN_Name") or f"Composition {index}")
    if name != target.get("compositionName"):
        raise SdkMutationStaleRevision("The exact Fusion composition name changed.")
    return item, comp


def _input(tool: Any, input_id: str) -> Any:
    for key, native_input in (tool.GetInputList() or {}).items():
        attrs = native_input.GetAttrs() or {}
        if attrs.get("INPS_ID") == input_id or str(key) == input_id:
            return native_input
    raise APICallFailed(f"Fusion input '{input_id}' is unavailable during lowering.")


def _output(tool: Any, output_id: str) -> Any:
    for key, native_output in (tool.GetOutputList() or {}).items():
        attrs = native_output.GetAttrs() or {}
        if attrs.get("OUTS_ID") == output_id or str(key) == output_id:
            return native_output
    raise APICallFailed(f"Fusion output '{output_id}' is unavailable during lowering.")


def _output_identity(native_output: Any) -> tuple[str, str, str]:
    try:
        output_attrs = native_output.GetAttrs() or {}
        tool_attrs = native_output.GetTool().GetAttrs() or {}
    except Exception as exc:
        raise APICallFailed("Fusion could not inspect a connection endpoint during readback.") from exc
    identity = (
        str(tool_attrs.get("TOOLS_Name") or ""),
        str(tool_attrs.get("TOOLS_RegID") or ""),
        str(output_attrs.get("OUTS_ID") or ""),
    )
    if not all(identity):
        raise APICallFailed("Fusion returned incomplete connection endpoint readback.")
    return identity


def _independent_graph_tools(comp: Any, graph: dict[str, Any]) -> dict[str, Any]:
    try:
        tools = list((comp.GetToolList(False) or {}).values())
    except Exception as exc:
        raise APICallFailed("Fusion could not independently enumerate the committed graph.") from exc
    by_name: dict[str, Any] = {}
    modifier_count = 0
    for tool in tools:
        attrs = tool.GetAttrs() or {}
        name = str(attrs.get("TOOLS_Name") or "")
        node_type = str(attrs.get("TOOLS_RegID") or "")
        if node_type == "BezierSpline":
            modifier_count += 1
            continue
        if not name or name in by_name:
            raise APICallFailed("Fusion committed an ambiguous graph node identity.")
        by_name[name] = tool
    expected_names = {row["id"] for row in graph["nodes"]}
    if set(by_name) != expected_names or modifier_count != len(graph["animations"]):
        raise APICallFailed("Fusion committed graph contents differ from the exact typed graph.")
    return by_name


def _assert_animation_readback(native_input: Any, expected_keyframes: list[dict[str, Any]]) -> None:
    connected_output = native_input.GetConnectedOutput()
    if connected_output is None:
        raise APICallFailed("Fusion structural readback found a missing animation spline.")
    try:
        modifier_attrs = connected_output.GetTool().GetAttrs() or {}
        raw_keyframes = native_input.GetKeyFrames() or {}
    except Exception as exc:
        raise APICallFailed("Fusion could not inspect the committed animation modifier.") from exc
    if modifier_attrs.get("TOOLS_RegID") != "BezierSpline" or not isinstance(raw_keyframes, dict):
        raise APICallFailed("Fusion structural readback found an unexpected animation modifier.")
    expected_by_time = {keyframe["time"]: keyframe["value"] for keyframe in expected_keyframes}
    actual_by_time: dict[int, Any] = {}
    for raw_time, raw_value in raw_keyframes.items():
        try:
            time = int(raw_time)
        except (TypeError, ValueError) as exc:
            raise APICallFailed("Fusion returned an invalid animation keyframe time.") from exc
        if isinstance(raw_time, float) and not raw_time.is_integer():
            raise APICallFailed("Fusion returned a non-integral animation keyframe time.")
        value = raw_value.get("Value") if isinstance(raw_value, dict) and "Value" in raw_value else raw_value
        actual_by_time[time] = list(value) if isinstance(value, tuple) else value
    if actual_by_time != expected_by_time:
        raise APICallFailed("Fusion structural readback found a keyframe-set mismatch.")


def _assert_exact_connection_readback(created: dict[str, Any], graph: dict[str, Any]) -> None:
    node_types = {row["id"]: row["type"] for row in graph["nodes"]}
    expected_connections = {
        (row["target"]["node"], row["target"]["port"]): (
            row["source"]["node"],
            node_types[row["source"]["node"]],
            row["source"]["port"],
        )
        for row in graph["connections"]
    }
    animated_inputs = {(row["node"], row["input"]) for row in graph["animations"]}
    actual_connections: dict[tuple[str, str], tuple[str, str, str]] = {}
    for node_id, tool in created.items():
        try:
            native_inputs = tool.GetInputList() or {}
        except Exception as exc:
            raise APICallFailed("Fusion could not enumerate exact committed graph connections.") from exc
        for key, native_input in native_inputs.items():
            attrs = native_input.GetAttrs() or {}
            input_id = str(attrs.get("INPS_ID") or key)
            try:
                connected_output = native_input.GetConnectedOutput()
            except Exception as exc:
                raise APICallFailed("Fusion could not inspect an exact committed graph connection.") from exc
            if connected_output is None or (node_id, input_id) in animated_inputs:
                continue
            actual_connections[(node_id, input_id)] = _output_identity(connected_output)
    if actual_connections != expected_connections:
        raise APICallFailed("Fusion structural readback found an unexpected or missing connection.")


def _assert_mutation_lock_contract(comp: Any) -> None:
    if not callable(getattr(comp, "Lock", None)) or not callable(getattr(comp, "Unlock", None)):
        raise APICallFailed("Fusion composition does not expose the required mutation lock contract.")


def _assert_undo_recovery_contract(comp: Any) -> None:
    if any(not callable(getattr(comp, method, None)) for method in ("StartUndo", "EndUndo", "Undo")):
        raise APICallFailed("Fusion composition does not expose the required recoverable undo contract.")


def _recover_failed_graph_mutation(
    comp: Any,
    before_graph: dict[str, Any],
    *,
    undo_closed: bool = False,
) -> str:
    """Commit the failed undo group, undo it, and prove the exact graph returned.

    Fusion's ``EndUndo(False)`` discards the undo event; it does not roll the
    enclosed mutations back. A failed destructive apply must therefore retain
    its undo event, execute that undo while the composition lock is still held,
    and compare a fresh native graph observation with the locked pre-state.
    """

    try:
        if not undo_closed:
            end_result = comp.EndUndo(True)
            if end_result is False:
                raise APICallFailed("Fusion rejected the failed graph mutation undo record.")
        undo_result = comp.Undo()
        if undo_result is False:
            raise APICallFailed("Fusion rejected recovery of the failed graph mutation.")
        recovered_graph = _fusion_graph_evidence(comp, None)
    except Exception as exc:
        if isinstance(exc, APICallFailed):
            raise
        raise APICallFailed("Fusion could not recover the failed graph mutation.") from exc
    if recovered_graph != before_graph:
        raise APICallFailed(
            "Fusion failed to restore the exact graph after a graph mutation error.",
            details={
                "recovery": "partial",
                "expected_graph_digest": _sha256(before_graph),
                "observed_graph_digest": _sha256(recovered_graph),
            },
        )
    return _sha256(recovered_graph)


def _apply_graph_transaction(comp: Any, graph: dict[str, Any], before_graph: dict[str, Any]) -> dict[str, Any]:
    """Destructively replace a graph with exact native undo recovery on error."""

    _assert_undo_recovery_contract(comp)
    undo_started = False
    undo_closed = False
    mutation_started = False
    try:
        comp.StartUndo("CutAgent SDK Fusion graph apply")
        undo_started = True
        for tool in list((comp.GetToolList(False) or {}).values()):
            mutation_started = True
            if not hasattr(tool, "Delete") or tool.Delete() is False:
                raise APICallFailed("Fusion could not remove an existing graph node.")
        created: dict[str, Any] = {}
        for row in graph["nodes"]:
            mutation_started = True
            tool = comp.AddTool(row["type"])
            if not tool:
                raise APICallFailed(f"Fusion could not create graph node type '{row['type']}'.")
            if hasattr(tool, "SetAttrs") and tool.SetAttrs({"TOOLS_Name": row["id"]}) is False:
                raise APICallFailed("Fusion could not assign an exact graph node identity.")
            created[row["id"]] = tool
            for input_id, value in row["inputs"].items():
                if tool.SetInput(input_id, value) is False:
                    raise APICallFailed("Fusion could not lower a graph input value.")
        for row in graph["connections"]:
            target_input = _input(created[row["target"]["node"]], row["target"]["port"])
            source_output = _output(created[row["source"]["node"]], row["source"]["port"])
            if target_input.ConnectTo(source_output) is False:
                raise APICallFailed("Fusion could not lower a graph connection.")
        for row in graph["animations"]:
            tool = created[row["node"]]
            native_input = _input(tool, row["input"])
            animation = row["animation"]
            spline = comp.BezierSpline()
            if not spline or native_input.ConnectTo(spline) is False:
                raise APICallFailed("Fusion could not attach an animation spline.")
            for keyframe in animation["keyframes"]:
                if tool.SetInput(row["input"], keyframe["value"], keyframe["time"]) is False:
                    raise APICallFailed("Fusion could not lower an animation keyframe.")
        end_result = comp.EndUndo(True)
        undo_closed = True
        if end_result is False:
            raise APICallFailed("Fusion rejected the completed graph mutation undo record.")
        undo_started = False
        return created
    except Exception as mutation_error:
        if undo_started:
            if mutation_started:
                try:
                    recovered_digest = _recover_failed_graph_mutation(comp, before_graph, undo_closed=undo_closed)
                except Exception as recovery_error:
                    recovery_details = getattr(recovery_error, "details", None)
                    if not isinstance(recovery_details, dict):
                        recovery_details = {"recovery": "unverified"}
                    raise APICallFailed(
                        "Fusion graph mutation failed and exact native recovery could not be proven.",
                        details={**recovery_details, "original_error": str(mutation_error)},
                    ) from recovery_error
                raise APICallFailed(
                    "Fusion graph mutation failed; the exact native graph was restored.",
                    details={
                        "recovery": "restored",
                        "recovered_graph_digest": recovered_digest,
                        "original_error": str(mutation_error),
                    },
                ) from mutation_error
            else:
                try:
                    comp.EndUndo(False)
                except Exception as recovery_error:
                    raise APICallFailed("Fusion could not close an unmodified undo transaction.") from recovery_error
        raise


def _exact_target_after_commit(conn: Any, target: dict[str, Any]) -> tuple[Any, Any]:
    try:
        return _exact_target(conn, target)
    except SdkMutationStaleRevision as exc:
        raise APICallFailed("The Fusion composition changed after the mutation committed.") from exc


def _native_value_matches(actual: Any, expected: Any) -> bool:
    """Compare authored arrays with Fusion's one-based point/color tables."""

    if not isinstance(expected, list):
        return actual == expected
    if isinstance(actual, (list, tuple)):
        return list(actual) == expected
    if not isinstance(actual, Mapping):
        return False
    indexed: dict[int, Any] = {}
    for key, value in actual.items():
        if isinstance(key, int) and not isinstance(key, bool):
            index = key
        elif isinstance(key, str) and key.isdigit():
            index = int(key)
        else:
            return False
        if index in indexed:
            return False
        indexed[index] = value
    required = set(range(1, len(expected) + 1))
    if not required.issubset(indexed) or [indexed[index] for index in sorted(required)] != expected:
        return False
    extras = set(indexed) - required
    return not extras or (len(expected) == 2 and extras == {3} and _finite_number(indexed[3]) and indexed[3] == 0)


def _readback(comp: Any, graph: dict[str, Any], created: dict[str, Any]) -> dict[str, Any]:
    nodes = []
    for row in graph["nodes"]:
        tool = created[row["id"]]
        attrs = tool.GetAttrs() or {}
        if str(attrs.get("TOOLS_RegID") or "") != row["type"]:
            raise APICallFailed("Fusion structural readback found a node-type mismatch.")
        values = {}
        for input_id, expected in row["inputs"].items():
            actual = tool.GetInput(input_id, 0)
            if not _native_value_matches(actual, expected):
                raise APICallFailed("Fusion structural readback found an input-value mismatch.")
            values[input_id] = actual
        nodes.append({"id": row["id"], "type": row["type"], "inputsDigest": _sha256(values)})
    _assert_exact_connection_readback(created, graph)
    for row in graph["animations"]:
        tool = created[row["node"]]
        native_input = _input(tool, row["input"])
        animation = row["animation"]
        _assert_animation_readback(native_input, animation["keyframes"])
        for keyframe in animation["keyframes"]:
            actual = tool.GetInput(row["input"], keyframe["time"])
            if not _native_value_matches(actual, keyframe["value"]):
                raise APICallFailed("Fusion structural readback found a keyframe-value mismatch.")
    return {
        "nodes": nodes,
        "connections": graph["connections"],
        "animatedInputs": len(graph["animations"]),
    }


def _protected_snapshot(conn: Any, fusion: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Capture neighboring state while redacting only the authorized target graph."""

    target_item = target["timelineItemNativeId"]
    target_index = target["compositionIndex"]
    protected_fusion = []
    for item in fusion.get("items", []):
        compositions = []
        for composition in item.get("compositions", []):
            row = {
                "index": composition.get("index"),
                "name": composition.get("name"),
                "graph": composition.get("graph"),
            }
            if item.get("native_item_id") == target_item and composition.get("index") == target_index:
                row["graph"] = "authorized-target-graph"
            compositions.append(row)
        protected_fusion.append({"native_item_id": item.get("native_item_id"), "compositions": compositions})
    timeline = timeline_ops.summarize_timeline(
        conn,
        window="all",
        max_runs=1,
        include_items=True,
        authoritative_track_state=True,
    )
    return {
        "projectNativeId": documented_unique_id(conn.project),
        "timelineNativeId": documented_unique_id(conn.timeline),
        "timeline": timeline,
        "fusion": protected_fusion,
    }


def apply_sdk_fusion_graph(conn: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Replace one exact composition inside a single native undo transaction."""

    if not isinstance(payload, dict) or set(payload) != {"target", "graph", "expectedGraphDigest"}:
        raise ValidationError("Private Fusion lowering payload is malformed.")
    target = payload.get("target")
    target_keys = {
        "projectNativeId", "timelineNativeId", "timelineItemNativeId", "compositionIndex",
        "compositionName", "nativeGraphEvidence", "recordStart", "recordEndExclusive",
    }
    if not isinstance(target, dict) or set(target) != target_keys or not isinstance(target.get("nativeGraphEvidence"), dict):
        raise ValidationError("Private Fusion lowering target is malformed.")
    for key in ("projectNativeId", "timelineNativeId", "timelineItemNativeId", "compositionName"):
        if not isinstance(target.get(key), str) or not target[key] or len(target[key]) > 4_096:
            raise ValidationError("Private Fusion lowering target identity is malformed.")
    for key in ("compositionIndex", "recordStart", "recordEndExclusive"):
        if not isinstance(target.get(key), int) or isinstance(target[key], bool):
            raise ValidationError("Private Fusion lowering target coordinate is malformed.")
    if not 1 <= target["compositionIndex"] <= 128 or target["recordEndExclusive"] <= target["recordStart"]:
        raise ValidationError("Private Fusion lowering target bounds are malformed.")
    registry = _registry()
    request = _validate_graph(payload["graph"], registry)
    before = inspect_fusion_compositions(conn, deadline_at_ms=None)
    matching_before = next(
        (row for row in before["items"] if row["native_item_id"] == payload["target"]["timelineItemNativeId"]),
        None,
    )
    before_comp = next(
        (row for row in (matching_before or {}).get("compositions", []) if row["index"] == payload["target"]["compositionIndex"]),
        None,
    )
    if before_comp is None:
        raise SdkMutationStaleRevision("The exact Fusion composition disappeared before execution.")
    if before_comp["graph"] != payload["target"].get("nativeGraphEvidence"):
        raise SdkMutationStaleRevision("The exact Fusion composition revision is stale.")
    _assert_expected_graph_digest(before_comp["graph"], payload["expectedGraphDigest"])
    protected_before = _protected_snapshot(conn, before, payload["target"])
    item, comp = _exact_target(conn, payload["target"])
    graph = request["graph"]
    locked = False
    try:
        _assert_mutation_lock_contract(comp)
        if comp.Lock() is False:
            raise APICallFailed("Fusion could not lock the exact composition for mutation.")
        locked = True
        locked_item, _ = _exact_target(conn, payload["target"])
        item = locked_item
        _assert_locked_graph_precondition(comp, before_comp["graph"], payload["expectedGraphDigest"])
        _apply_graph_transaction(comp, graph, before_comp["graph"])
    finally:
        if locked:
            try:
                unlock_result = comp.Unlock()
            except Exception as exc:
                raise APICallFailed("Fusion could not release the exact composition mutation lock.") from exc
            if unlock_result is False:
                raise APICallFailed("Fusion could not release the exact composition mutation lock.")

    _, committed_comp = _exact_target_after_commit(conn, payload["target"])
    structural = _readback(committed_comp, graph, _independent_graph_tools(committed_comp, graph))
    after = inspect_fusion_compositions(conn, deadline_at_ms=None)
    matching_after = next(
        (row for row in after["items"] if row["native_item_id"] == payload["target"]["timelineItemNativeId"]),
        None,
    )
    after_comp = next(
        (row for row in (matching_after or {}).get("compositions", []) if row["index"] == payload["target"]["compositionIndex"]),
        None,
    )
    if after_comp is None:
        raise APICallFailed("The exact Fusion composition disappeared during structural readback.")
    protected_after = _protected_snapshot(conn, after, payload["target"])
    protected_before_digest = _sha256(protected_before)
    protected_after_digest = _sha256(protected_after)
    applied_graph_digest = _sha256(request)
    live_graph_digest = _sha256(after_comp["graph"])
    return {
        "registryDigest": request["registryDigest"],
        "appliedGraphDigest": applied_graph_digest,
        "readback": {"graphDigest": live_graph_digest, **structural},
        "nativeGraphEvidence": after_comp["graph"],
        "protectedState": {
            "projectNativeId": documented_unique_id(conn.project),
            "timelineNativeId": documented_unique_id(conn.timeline),
            "timelineItemNativeId": documented_unique_id(item),
            "otherFusionCompositionCount": max(0, int(item.GetFusionCompCount() or 0) - 1),
            "beforeDigest": protected_before_digest,
            "afterDigest": protected_after_digest,
            "preserved": protected_before_digest == protected_after_digest,
        },
    }
