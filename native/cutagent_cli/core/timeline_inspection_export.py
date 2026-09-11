"""On-demand, explicit timeline inspection export.

This document is deliberately separate from the compact SDK timeline snapshot.
It records everything the active DaVinci Resolve runtime can read without
pretending that the result can reconstruct the timeline.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Callable

from ..errors import APICallFailed, ValidationError
from . import (
    audio_clip_effect_readback,
    clip_speed_db,
    color_primary_readback,
    color_resolvefx_readback,
    db_session,
    db_timeline_rows,
    edit_insert_overwrite,
    fairlight_ops,
    keyframe_db,
    keyframe_ops,
    nested_media_db,
    native_channel_mapping,
    retime_curve_readback,
    sdk_live_inspection,
    timeline_ops,
    video_fade_readback,
)
from .db_timeline_selection import LiveItemRef


SCHEMA = "cutagent.timeline-inspection/v1"
REQUESTED_DOMAINS = (
    "timeline",
    "tracks",
    "items",
    "properties",
    "fades",
    "keyframes",
    "fusion",
    "color",
    "fairlight",
    "retime",
    "nesting",
    "multicam",
    "transitions",
    "effects",
    "revisions",
)
_KEYFRAME_PROPERTIES = tuple(
    dict.fromkeys((*keyframe_ops._VIDEO_PROPERTIES, *keyframe_ops._AUDIO_PROPERTIES))
)
_MAX_COLLECTION = 100_000
_MAX_TEXT = 1_000_000
_MAX_NESTING_DEPTH = 64


def _bounded_json(value: Any, *, depth: int = 0) -> Any:
    """Convert native values into bounded JSON without stringifying objects."""

    if depth > _MAX_NESTING_DEPTH:
        raise ValueError("maximum nesting depth exceeded")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numeric value")
        return value
    if isinstance(value, str):
        if len(value) > _MAX_TEXT:
            raise ValueError("text value exceeds the export bound")
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_COLLECTION:
            raise ValueError("collection exceeds the export bound")
        return [_bounded_json(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > _MAX_COLLECTION:
            raise ValueError("mapping exceeds the export bound")
        return {
            str(key): _bounded_json(item, depth=depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    raise ValueError(f"unsupported native value type: {type(value).__name__}")


class _Collector:
    def __init__(self) -> None:
        self.unreadable: list[dict[str, str]] = []
        self.domain_counts = {domain: {"available": 0, "unavailable": 0} for domain in REQUESTED_DOMAINS}

    def available(self, domain: str) -> None:
        self.domain_counts[domain]["available"] += 1

    def missing(self, domain: str, path: str, reason: str, method: str | None = None) -> None:
        row = {"path": path, "domain": domain, "reason": reason}
        if method:
            row["method"] = method
        self.unreadable.append(row)
        self.domain_counts[domain]["unavailable"] += 1

    def call(
        self,
        domain: str,
        path: str,
        native: Any,
        method: str,
        *args: Any,
        empty_is_available: bool = False,
    ) -> Any:
        callback = getattr(native, method, None)
        if not callable(callback):
            self.missing(domain, path, "method_unavailable", method)
            return None
        try:
            value = callback(*args)
        except Exception:
            self.missing(domain, path, "call_failed", method)
            return None
        # False is a legitimate native readback for toggles such as track lock,
        # track enablement, and Color-node enablement. Only absence is missing.
        if value is None and not empty_is_available:
            self.missing(domain, path, "readback_unavailable", method)
            return None
        try:
            normalized = _bounded_json(value)
        except (TypeError, ValueError):
            self.missing(domain, path, "invalid_or_unserializable_value", method)
            return None
        self.available(domain)
        return normalized

    def report(self) -> dict[str, Any]:
        domains = {}
        for domain, counts in self.domain_counts.items():
            if counts["available"] == 0 and counts["unavailable"] == 0:
                status = "not_applicable"
            elif counts["unavailable"] == 0:
                status = "available"
            elif counts["available"] == 0:
                status = "unavailable"
            else:
                status = "partial"
            domains[domain] = {"status": status, **counts}
        return {
            "complete": not self.unreadable,
            "domains": domains,
            "unreadableFieldCount": len(self.unreadable),
            "unreadableFields": sorted(self.unreadable, key=lambda row: (row["path"], row["reason"])),
        }


class _PersistedItemReader:
    """One read-only Project.db snapshot, with exact native-item binding."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self.connection: sqlite3.Connection | None = None
        self.project_db_path: str | None = None
        self.timeline_name = str(conn.timeline.GetName() or "")

    def __enter__(self) -> "_PersistedItemReader":
        current = db_session.resolve_current_disk_project_db(
            self.conn, allow_project_name_inference=True,
        )
        self.project_db_path = str(Path(current["project_db_path"]).resolve())
        uri = Path(self.project_db_path).as_uri() + "?mode=ro"
        self.connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("BEGIN")
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def timeline_output(self, identity: str) -> dict[str, Any]:
        """Read exact sequence output fields, not inferred bus identities."""
        if self.connection is None or not identity:
            raise LookupError("Exact timeline identity is unavailable.")
        rows = self.connection.execute(
            "SELECT s.OutputAudioGain, s.NumOutputAudioChannels "
            "FROM Sm2Timeline t JOIN Sm2Sequence s ON s.Sm2Sequence_id = t.Sequence "
            "WHERE t.Sm2Timeline_id = ? AND s.Sm2Timeline_id = t.Sm2Timeline_id",
            (identity,),
        ).fetchall()
        if len(rows) != 1:
            raise LookupError("Persisted timeline output identity is unavailable or ambiguous.")
        gain, channels = rows[0]
        if isinstance(gain, bool) or not isinstance(gain, (int, float)) or not math.isfinite(gain):
            raise ValueError("Persisted timeline output gain is unavailable.")
        if isinstance(channels, bool) or not isinstance(channels, int) or channels < 0:
            raise ValueError("Persisted timeline output channel count is unavailable.")
        return {
            "gainDb": gain,
            "channelCount": channels,
            "source": "identity-bound Sm2Sequence output fields",
            "busRoutingProven": False,
        }

    def row(
        self,
        *,
        track_type: str,
        track_index: int,
        identity: str,
        name: str,
        start: int,
        duration: int,
    ) -> dict[str, Any]:
        if self.connection is None:
            raise LookupError("Project.db reader is unavailable.")
        item_ref = LiveItemRef(
            track_type, track_index, name, start, duration, item_id=identity,
        )
        row = db_timeline_rows.find_ti_item_row(
            self.connection.cursor(),
            item=item_ref,
            db_type="Sm2TiVideoClip" if track_type == "video" else "Sm2TiAudioClip",
            timeline_name=self.timeline_name,
        )
        if str(row.get("Sm2TiItem_id") or "") != identity:
            raise LookupError("Project.db item identity does not match the live native item.")
        return row


def _nested_structure(
    collector: _Collector,
    persisted: _PersistedItemReader | None,
    *,
    domain: str,
    path: str,
    media_id: str | None,
    wrapper_item_id: str | None,
) -> dict[str, Any] | None:
    field = "angleStructure" if domain == "multicam" else "childStructure"
    target_path = f"{path}.{domain}.{field}"
    if persisted is None or not persisted.project_db_path:
        collector.missing(domain, target_path, "project_db_readback_unavailable")
        return None
    if not media_id:
        collector.missing(domain, target_path, "exact_media_identity_unavailable")
        return None
    if not wrapper_item_id:
        collector.missing(domain, target_path, "exact_wrapper_identity_unavailable")
        return None
    try:
        graph = nested_media_db.inspect_nested_media_graph(
            persisted.project_db_path,
            media_id=media_id,
            wrapper_item_id=wrapper_item_id,
        )
        graph = _bounded_json(graph)
    except Exception as exc:
        reason = getattr(exc, "details", {}).get("reason") if hasattr(exc, "details") else None
        collector.missing(domain, target_path, str(reason or "persisted_readback_failed"))
        return None
    collector.available(domain)

    def register_unsupported(node: Any, node_path: str) -> None:
        if not isinstance(node, dict):
            return
        if node.get("status") == "unsupported":
            collector.missing(
                domain,
                node_path,
                str(node.get("reason") or "nested_structure_not_decoded"),
                "strict persisted nested-media readback",
            )
        for index, unsupported in enumerate(node.get("unsupported") or []):
            if not isinstance(unsupported, dict):
                continue
            collector.missing(
                domain,
                f"{node_path}.unsupported[{index}].{unsupported.get('path') or 'unknown'}",
                str(unsupported.get("reason") or "not_decoded"),
                "strict persisted nested-media readback",
            )
        for nested_id, nested in (node.get("nested_media") or {}).items():
            register_unsupported(nested, f"{node_path}.nestedMedia[{nested_id}]")
        register_unsupported(node.get("wrapper"), f"{node_path}.wrapper")

    register_unsupported(graph, target_path)
    return graph

def _item_identity(item: Any) -> str | None:
    return sdk_live_inspection.documented_unique_id(item)


def _persisted_item_classification(
    persisted: _PersistedItemReader | None,
    *,
    track_type: str,
    track_index: int,
    identity: str | None,
    name: str | None,
    start: Any,
    duration: Any,
) -> dict[str, str] | None:
    """Return only exact, reviewed persisted item-kind discriminators."""

    if (
        persisted is None
        or track_type != "video"
        or not identity
        or not name
        or isinstance(start, bool)
        or not isinstance(start, int)
        or isinstance(duration, bool)
        or not isinstance(duration, int)
    ):
        return None
    try:
        row = persisted.row(
            track_type=track_type,
            track_index=track_index,
            identity=identity,
            name=name,
            start=start,
            duration=duration,
        )
    except Exception:
        return None
    pretty_type = row.get("PrettyType")
    kind = {"Fusion Title": "fusion_title", "Fusion Composition": "fusion_composition"}.get(pretty_type)
    if kind is None:
        return None
    return {
        "kind": kind,
        "prettyType": pretty_type,
        "source": "exact persisted item identity",
    }


def _persisted_audio_effects(
    collector: _Collector,
    persisted: _PersistedItemReader | None,
    *,
    identity: str | None,
    path: str,
) -> dict[str, Any] | None:
    if persisted is None or persisted.connection is None or not identity:
        collector.missing(
            "effects", f"{path}.effects.persistedAudio",
            "exact_persisted_item_readback_unavailable",
            "strict persisted audio clip effect readback",
        )
        return None
    try:
        result = audio_clip_effect_readback.read_audio_clip_effects(
            persisted.connection.cursor(), item_id=identity,
        )
        normalized = _bounded_json(result)
    except Exception:
        collector.missing(
            "effects", f"{path}.effects.persistedAudio",
            "strict_persisted_effect_readback_failed",
            "strict persisted audio clip effect readback",
        )
        return None

    clip_fx = normalized.get("clipFx") if isinstance(normalized, dict) else None
    archive_eq = normalized.get("archiveEq") if isinstance(normalized, dict) else None
    unknown_filters = normalized.get("unknownEffectFilters") if isinstance(normalized, dict) else None
    if isinstance(clip_fx, dict):
        exact_parameters = clip_fx.get("exactFixtureParameters") or {}
        for index, plugin in enumerate(clip_fx.get("plugins") or []):
            if not isinstance(plugin, dict):
                continue
            collector.available("effects")
            plugin_id = plugin.get("pluginId")
            if plugin_id not in exact_parameters:
                collector.missing(
                    "effects",
                    f"{path}.effects.persistedAudio.clipFx.plugins[{index}].parameters",
                    "parameter_values_not_strictly_decodable",
                    "strict FL::ClipFX parameter layout",
                )
            else:
                collector.available("effects")
    if isinstance(archive_eq, dict):
        collector.available("effects")
    if isinstance(unknown_filters, dict):
        collector.missing(
            "effects", f"{path}.effects.persistedAudio.unknownEffectFilters.semanticIdentity",
            "unrecognized_persisted_effect_filter_payload",
            "exact retained audio EQ fixture match",
        )
    if clip_fx is None and archive_eq is None and unknown_filters is None:
        collector.available("effects")
    return normalized


def _covered_mapping_value(
    collector: _Collector,
    domain: str,
    path: str,
    mapping: dict[str, Any] | None,
    key: str,
    *,
    reason: str,
) -> Any:
    value = mapping.get(key) if isinstance(mapping, dict) else None
    if value is None:
        collector.missing(domain, path, reason)
        return None
    try:
        normalized = _bounded_json(value)
    except (TypeError, ValueError):
        collector.missing(domain, path, "invalid_or_unserializable_value")
        return None
    collector.available(domain)
    return normalized


def _media_pool_details(collector: _Collector, item: Any, path: str) -> tuple[Any, dict[str, Any]]:
    getter = getattr(item, "GetMediaPoolItem", None)
    native_media = None
    if not callable(getter):
        collector.missing("items", f"{path}.mediaPoolItem", "method_unavailable", "GetMediaPoolItem")
    else:
        try:
            native_media = getter()
        except Exception:
            collector.missing("items", f"{path}.mediaPoolItem", "call_failed", "GetMediaPoolItem")
    if native_media is None:
        if callable(getter):
            collector.missing("items", f"{path}.mediaPoolItem", "readback_unavailable", "GetMediaPoolItem")
        return None, {"id": None, "name": None, "properties": None}
    collector.available("items")
    media_id = sdk_live_inspection.media_pool_native_id(native_media)
    if media_id:
        collector.available("items")
    else:
        collector.missing("items", f"{path}.mediaPoolItem.id", "readback_unavailable", "GetMediaId/GetUniqueId")
    return native_media, {
        "id": media_id,
        "name": collector.call("items", f"{path}.mediaPoolItem.name", native_media, "GetName", empty_is_available=False),
        "properties": collector.call(
            "properties", f"{path}.mediaPoolItem.properties", native_media,
            "GetClipProperty", empty_is_available=False,
        ),
    }


def _keyframes(
    collector: _Collector,
    conn: Any,
    persisted: _PersistedItemReader | None,
    item: Any,
    path: str,
    *,
    track_type: str,
    item_name: str | None,
    identity: str | None,
    track_index: int,
    authoritative_source: dict[str, Any] | None,
    audio_envelopes_by_id: dict[str, dict[str, Any]] | None = None,
    audio_envelope_cache_complete: bool = False,
    timeline_resolution: tuple[int, int] | None = None,
) -> dict[str, Any] | None:
    required = ("GetKeyframeCount", "GetKeyframeAtIndex", "GetPropertyAtKeyframeIndex")
    missing = [method for method in required if not callable(getattr(item, method, None))]
    if missing:
        try:
            if track_type == "audio":
                if not identity or audio_envelopes_by_id is None:
                    raise ValueError
                envelope = audio_envelopes_by_id.get(identity)
                if envelope is None and not audio_envelope_cache_complete:
                    raise ValueError
                result = {"Volume": envelope.get("points", [])} if envelope else {}
            else:
                if (
                    persisted is None
                    or not identity
                    or not item_name
                    or not authoritative_source
                    or timeline_resolution is None
                ):
                    raise ValueError
                row = persisted.row(
                    track_type=track_type,
                    track_index=track_index,
                    identity=identity,
                    name=item_name,
                    start=int(authoritative_source["start"]),
                    duration=int(authoritative_source["duration"]),
                )
                _extra, groups = keyframe_db._decode_effect_filters(row.get("EffectFiltersBA"))
                result = {}
                for spec in keyframe_db._VIDEO_PROPERTY_SPECS.values():
                    origin = keyframe_db._row_keyframe_origin(row, spec)
                    points = keyframe_db._read_points_from_groups(groups, spec, frame_origin=origin)
                    if points:
                        result[spec.public_name] = [
                            point.to_dict(
                                item_start=int(authoritative_source["start"]),
                                spec=spec,
                                resolution=timeline_resolution,
                            )
                            for point in points
                        ]
            if not isinstance(result, dict):
                raise ValueError
            collector.available("keyframes")
            return _bounded_json(result)
        except Exception:
            collector.missing(
                "keyframes", f"{path}.keyframes", "native_and_db_readback_unavailable",
                f"{','.join(missing)}; Project.db keyframe readback",
            )
            return None
    result: dict[str, Any] = {}
    for property_name in _KEYFRAME_PROPERTIES:
        try:
            rows = keyframe_ops._collect_property_keyframes(item, property_name)
            result[property_name] = _bounded_json(rows)
            collector.available("keyframes")
        except Exception:
            collector.missing("keyframes", f"{path}.keyframes.{property_name}", "call_failed", "TimelineItem keyframe API")
    return result


def _retime_curve(
    collector: _Collector,
    conn: Any,
    persisted: _PersistedItemReader | None,
    path: str,
    *,
    track_type: str,
    track_index: int,
    item_name: str | None,
    identity: str | None,
    authoritative_source: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if track_type not in {"video", "audio"}:
        collector.missing("retime", f"{path}.retime.curve", "not_applicable_to_track_type")
        return None
    try:
        if persisted is None or not identity or not item_name or not authoritative_source:
            raise ValueError
        start = int(authoritative_source["start"])
        duration = int(authoritative_source["duration"])
        row = persisted.row(
            track_type=track_type,
            track_index=track_index,
            identity=identity,
            name=item_name,
            start=start,
            duration=duration,
        )
        state = clip_speed_db.normalized_time_map_state(
            row,
            fps=float(conn.fps),
            record_start_frame=start,
            fallback_duration_frames=duration,
        )
        curve = retime_curve_readback.curve_coordinates(
            state,
            record_start=start,
            source_start=state["native_record_origin_seconds"] * state["source_fps"],
        )
        if not isinstance(curve, dict):
            raise ValueError
        collector.available("retime")
        return _bounded_json(curve)
    except Exception:
        collector.missing(
            "retime", f"{path}.retime.curve", "db_readback_unavailable",
            "Project.db persisted time-map readback",
        )
        return None


def _fusion(collector: _Collector, item: Any, path: str) -> list[dict[str, Any]] | None:
    count = collector.call("fusion", f"{path}.fusion.count", item, "GetFusionCompCount")
    if count is None:
        return None
    try:
        count_value = int(count)
    except (TypeError, ValueError):
        collector.missing("fusion", f"{path}.fusion.count", "invalid_value", "GetFusionCompCount")
        return None
    if count_value < 0 or count_value > 128:
        collector.missing("fusion", f"{path}.fusion.count", "out_of_bounds", "GetFusionCompCount")
        return None
    rows = []
    for index in range(1, count_value + 1):
        getter = getattr(item, "GetFusionCompByIndex", None)
        if not callable(getter):
            collector.missing("fusion", f"{path}.fusion.compositions[{index - 1}]", "method_unavailable", "GetFusionCompByIndex")
            continue
        try:
            comp = getter(index)
            attrs = comp.GetAttrs() if comp is not None else None
            if comp is None or not isinstance(attrs, dict):
                raise ValueError
            try:
                graph = sdk_live_inspection._fusion_graph_evidence(comp, None)
            except Exception:
                graph = None
                collector.missing("fusion", f"{path}.fusion.compositions[{index - 1}].graph",
                                  "call_failed", "Fusion composition graph readback")
            # CopySettings returns a native settings table, unlike Copy which
            # changes the system clipboard. Pass every tool explicitly so user
            # selection cannot accidentally limit the inspected composition.
            native_settings = None
            try:
                tools = comp.GetToolList(False)
                if not isinstance(tools, dict):
                    raise ValueError("invalid Fusion tool list")
            except Exception:
                collector.missing("fusion", f"{path}.fusion.compositions[{index - 1}].nativeSettings",
                                  "call_failed", "GetToolList")
            else:
                native_settings = collector.call(
                    "fusion", f"{path}.fusion.compositions[{index - 1}].nativeSettings",
                    comp, "CopySettings", tools,
                )
            rows.append({
                "index": index,
                "name": str(attrs.get("COMPS_Name") or attrs.get("COMPN_Name") or f"Composition {index}"),
                "graph": graph,
                "nativeSettings": native_settings,
                "graphDigest": sdk_live_inspection.fusion_graph_digest(graph) if graph is not None else None,
            })
            collector.available("fusion")
        except Exception:
            collector.missing("fusion", f"{path}.fusion.compositions[{index - 1}]", "call_failed", "Fusion composition graph readback")
    return rows


def _color_nodes(collector, node_source, color_path, primary_readback):
    node_count = collector.call("color", f"{color_path}.nodeCount", node_source, "GetNumNodes")
    nodes = []
    if isinstance(node_count, int) and 0 <= node_count <= 4096:
        for index in range(1, node_count + 1):
            node_path = f"{color_path}.nodes[{index - 1}]"
            primary_controls = None
            if isinstance(primary_readback, dict) and primary_readback.get("status") == "available":
                primary_controls = (primary_readback.get("primaryControlsByNode") or {}).get(str(index), {})
                collector.available("color")
            else:
                collector.missing(
                    "color", f"{node_path}.primaryControls",
                    str((primary_readback or {}).get("reason") or "project_db_color_primary_readback_unavailable"),
                    "Project.db Color primary-control readback",
                )
            effects = None
            effects_getter = getattr(node_source, "GetToolsInNode", None)
            if not callable(effects_getter):
                collector.missing("color", f"{node_path}.effects", "method_unavailable", "GetToolsInNode")
            else:
                try:
                    raw_effects = effects_getter(index)
                    if raw_effects is None:
                        collector.missing(
                            "color", f"{node_path}.effects",
                            "readback_unavailable", "GetToolsInNode",
                        )
                        effect_names = None
                    else:
                        effects_ok, effect_names = sdk_live_inspection._tool_names(raw_effects)
                        if not effects_ok:
                            raise ValueError
                        collector.available("color")
                    effects = effect_names
                except Exception:
                    collector.missing("color", f"{node_path}.effects", "invalid_or_unserializable_value", "GetToolsInNode")
            enabled_map = (primary_readback or {}).get("nodeEnabledByNode") or {}
            persisted_enabled = enabled_map.get(str(index))
            if isinstance(persisted_enabled, bool):
                enabled = persisted_enabled
                enabled_source = "persisted_active_grade"
                collector.available("color")
            else:
                enabled = collector.call("color", f"{node_path}.enabled", node_source, "GetNodeEnabled", index)
                enabled_source = "native_api" if isinstance(enabled, bool) else None
            nodes.append({
                "index": index,
                "label": collector.call("color", f"{node_path}.label", node_source, "GetNodeLabel", index),
                "enabled": enabled,
                "enabledSource": enabled_source,
                "lut": collector.call("color", f"{node_path}.lut", node_source, "GetLUT", index),
                "cacheMode": collector.call("color", f"{node_path}.cacheMode", node_source, "GetNodeCacheMode", index),
                "effects": effects,
                "primaryControls": primary_controls,
            })
    elif node_count is not None:
        collector.missing("color", f"{color_path}.nodes", "invalid_value", "GetNumNodes")
    return node_count, nodes


def _native_color_graph(collector, owner, method, path):
    getter = getattr(owner, method, None)
    if not callable(getter):
        collector.missing("color", path, "method_unavailable", method)
        return None
    try:
        graph = getter()
    except Exception:
        collector.missing("color", path, "call_failed", method)
        return None
    if graph is None:
        collector.missing("color", path, "node_graph_unavailable", method)
        return None
    count, nodes = _color_nodes(collector, graph, path, None)
    return {"nodeCount": count, "nodes": nodes}


def _color(
    collector: _Collector,
    item: Any,
    path: str,
    primary_readback: dict[str, Any] | None,
    resolvefx_readback: dict[str, Any] | None,
    *, project: Any = None,
) -> dict[str, Any]:
    cache_path = f"{path}.color.outputCacheEnabled"
    cache_getter = getattr(item, "GetIsColorOutputCacheEnabled", None)
    output_cache_enabled = None
    if not callable(cache_getter):
        collector.missing(
            "color", cache_path, "method_unavailable", "GetIsColorOutputCacheEnabled",
        )
    else:
        try:
            cache_value = cache_getter()
        except Exception:
            collector.missing(
                "color", cache_path, "call_failed", "GetIsColorOutputCacheEnabled",
            )
        else:
            # Studio 21.1 returns integer 0/1 despite the bool stub annotation.
            # Match the native cache owner without coercing arbitrary values.
            if isinstance(cache_value, bool) or (
                type(cache_value) is int and cache_value in (0, 1)
            ):
                output_cache_enabled = bool(cache_value)
                collector.available("color")
            else:
                collector.missing(
                    "color", cache_path,
                    "readback_unavailable" if cache_value is None else "invalid_value",
                    "GetIsColorOutputCacheEnabled",
                )
    graph = None
    graph_getter = getattr(item, "GetNodeGraph", None)
    if callable(graph_getter):
        try:
            graph = graph_getter()
        except Exception:
            collector.missing("color", f"{path}.color.nodeGraph", "call_failed", "GetNodeGraph")
    node_source = graph if graph is not None else item
    node_count, nodes = _color_nodes(collector, node_source, f"{path}.color", primary_readback)
    collector.missing(
        "color", f"{path}.color.connectivity",
        "complete_color_graph_connectivity_not_decoded",
        "persisted container and encoded edge evidence is partial",
    )
    layer_count = None
    layers = [{"index": 1, "nodeCount": node_count, "nodes": nodes}]
    if project is not None:
        raw_count = collector.call("color", f"{path}.color.layerCount", project, "GetSetting", "nodeStackLayers")
        if isinstance(raw_count, str) and raw_count.isdecimal():
            layer_count = int(raw_count)
        elif isinstance(raw_count, int) and not isinstance(raw_count, bool):
            layer_count = raw_count
        if layer_count is None or not 1 <= layer_count <= 64:
            layer_count = None
            collector.missing("color", f"{path}.color.layerCount", "invalid_or_unavailable_layer_count", "GetSetting(nodeStackLayers)")
        else:
            for layer in range(2, layer_count + 1):
                layer_path = f"{path}.color.layers[{layer - 1}]"
                try:
                    layer_graph = graph_getter(layer) if callable(graph_getter) else None
                except Exception:
                    layer_graph = None
                if layer_graph is None:
                    collector.missing("color", layer_path, "node_graph_unavailable", "GetNodeGraph(layer)")
                    layers.append({"index": layer, "nodeCount": None, "nodes": None})
                    continue
                count, layer_nodes = _color_nodes(collector, layer_graph, layer_path, None)
                layers.append({"index": layer, "nodeCount": count, "nodes": layer_nodes})
    native_group = None
    getter = getattr(item, "GetColorGroup", None)
    if not callable(getter):
        collector.missing("color", f"{path}.color.groupName", "method_unavailable", "GetColorGroup")
    else:
        try:
            native_group = getter()
        except Exception:
            collector.missing("color", f"{path}.color.groupName", "call_failed", "GetColorGroup")
    group_name = None
    group_graphs = None
    if native_group not in (None, False):
        group_name = collector.call("color", f"{path}.color.groupName", native_group, "GetName")
        group_graphs = {
            "preClip": _native_color_graph(collector, native_group, "GetPreClipNodeGraph", f"{path}.color.groupGraphs.preClip"),
            "postClip": _native_color_graph(collector, native_group, "GetPostClipNodeGraph", f"{path}.color.groupGraphs.postClip"),
        }
    elif callable(getter):
        collector.available("color")
    local_versions = collector.call("color", f"{path}.color.versions.local", item, "GetVersionNameList", 0)
    remote_versions = collector.call("color", f"{path}.color.versions.remote", item, "GetVersionNameList", 1)
    current_version = collector.call("color", f"{path}.color.currentVersion", item, "GetCurrentVersion")
    resolvefx = None
    if isinstance(resolvefx_readback, dict) and resolvefx_readback.get("status") == "available":
        resolvefx = {
            "effects": resolvefx_readback.get("effects") or [],
            "source": resolvefx_readback.get("source"),
        }
        collector.available("color")
        for effect_index, effect in enumerate(resolvefx["effects"]):
            collector.available("color")
            for setting_index, setting in enumerate(effect.get("settings") or []):
                if setting.get("status") == "available":
                    collector.available("color")
                else:
                    collector.missing(
                        "color",
                        f"{path}.color.resolveFx.effects[{effect_index}].settings[{setting_index}]",
                        str(setting.get("reason") or "resolvefx_setting_readback_unavailable"),
                        "strict persisted ResolveFX setting readback",
                    )
    else:
        collector.missing(
            "color", f"{path}.color.resolveFx",
            str((resolvefx_readback or {}).get("reason") or "project_db_resolvefx_readback_unavailable"),
            "exact persisted ResolveFX readback",
        )
    return {
        "outputCacheEnabled": output_cache_enabled,
        "nodeCount": node_count,
        "nodes": nodes,
        "layerCount": layer_count,
        "layers": layers,
        "persistedTopologyEvidence": (primary_readback or {}).get("topologyEvidence"),
        "versions": {"local": local_versions, "remote": remote_versions},
        "currentVersion": current_version,
        "groupName": group_name,
        "groupGraphs": group_graphs,
        "resolveFx": resolvefx,
    }


def _takes(collector: _Collector, item: Any, path: str) -> dict[str, Any]:
    selected = collector.call("items", f"{path}.takes.selectedIndex", item, "GetSelectedTakeIndex")
    count = collector.call("items", f"{path}.takes.count", item, "GetTakesCount")
    if isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= _MAX_COLLECTION:
        rows = []
        for index in range(1, count + 1):
            getter = getattr(item, "GetTakeByIndex", None)
            if not callable(getter):
                collector.missing("items", f"{path}.takes.items[{index - 1}]", "method_unavailable", "GetTakeByIndex")
                continue
            try:
                take = getter(index)
                if not isinstance(take, dict):
                    raise ValueError
                media = take.get("mediaPoolItem")
                rows.append({
                    "index": index,
                    "selected": selected == index,
                    "startFrame": _bounded_json(take.get("startFrame")),
                    "endFrame": _bounded_json(take.get("endFrame")),
                    "mediaPoolItem": {
                        "id": sdk_live_inspection.media_pool_native_id(media) if media is not None else None,
                        "name": (
                            collector.call("items", f"{path}.takes.items[{index - 1}].mediaPoolItem.name", media, "GetName")
                            if media is not None else None
                        ),
                    },
                })
                collector.available("items")
            except Exception:
                collector.missing("items", f"{path}.takes.items[{index - 1}]", "call_failed", "GetTakeByIndex")
        return {"selectedIndex": selected, "count": count, "items": rows}
    if count is not None:
        collector.missing("items", f"{path}.takes.count", "invalid_value", "GetTakesCount")
    legacy = collector.call("items", f"{path}.takes.items", item, "GetTakeList")
    return {"selectedIndex": selected, "count": None, "items": legacy}


def _item_row(
    collector: _Collector,
    conn: Any,
    persisted: _PersistedItemReader | None,
    item: Any,
    *,
    track_type: str,
    track_index: int,
    item_index: int,
    authoritative_source: dict[str, Any] | None = None,
    video_fade: dict[str, Any] | None = None,
    color_primary: dict[str, Any] | None = None,
    color_resolvefx: dict[str, Any] | None = None,
    audio_envelopes_by_id: dict[str, dict[str, Any]] | None = None,
    audio_envelope_cache_complete: bool = False,
    timeline_resolution: tuple[int, int] | None = None,
) -> dict[str, Any]:
    path = f"tracks.{track_type}[{track_index}].items[{item_index}]"
    identity = _item_identity(item)
    item_name = collector.call("items", f"{path}.name", item, "GetName", empty_is_available=False)
    record_start = collector.call("items", f"{path}.record.start", item, "GetStart")
    record_end = collector.call("items", f"{path}.record.endExclusive", item, "GetEnd")
    record_duration = collector.call("items", f"{path}.record.duration", item, "GetDuration")
    media, media_details = _media_pool_details(collector, item, path)
    item_properties = collector.call(
        "properties", f"{path}.properties", item, getattr(collector, "item_properties_method", "GetProperty"),
        empty_is_available=False,
    )
    native_211 = getattr(collector, "item_properties_method", "GetProperty") == "GetProperties"
    native_fades = None
    native_speed = None
    if native_211:
        fades = collector.call("fades", f"{path}.fades", item, "GetFades", empty_is_available=False)
        native_fades = fades
        native_speed = collector.call("retime", f"{path}.retime.nativeSpeed", item, "GetSpeed")
        if isinstance(item_properties, dict) and isinstance(fades, dict):
            item_properties = {**item_properties, **{key: fades[key] for key in ("FadeIn", "FadeOut") if key in fades}}
    media_type = None
    if isinstance(media_details.get("properties"), dict):
        media_type = media_details["properties"].get("Type")
    persisted_classification = _persisted_item_classification(
        persisted,
        track_type=track_type,
        track_index=track_index,
        identity=identity,
        name=item_name if isinstance(item_name, str) else None,
        start=record_start,
        duration=record_duration,
    )
    nesting_kind = "unknown"
    folded_type = str(media_type or "").casefold()
    if "multicam" in folded_type:
        nesting_kind = "multicam"
        collector.available("multicam")
    elif "compound" in folded_type or "timeline" in folded_type:
        nesting_kind = "nested_timeline"
        collector.available("nesting")
    elif folded_type:
        nesting_kind = "none"
        collector.available("nesting")
        collector.available("multicam")
    elif persisted_classification and persisted_classification["kind"] in {"fusion_title", "fusion_composition"}:
        nesting_kind = "none"
        collector.available("nesting")
        collector.available("multicam")
    else:
        collector.missing("nesting", f"{path}.nesting.kind", "media_type_unavailable")
        collector.missing("multicam", f"{path}.multicam.isMulticam", "media_type_unavailable")
    nested_structure = None
    if nesting_kind != "none" and nesting_kind != "unknown":
        domain = "multicam" if nesting_kind == "multicam" else "nesting"
        nested_structure = _nested_structure(
            collector,
            persisted,
            domain=domain,
            path=path,
            media_id=(str(media_details.get("id") or "") or None),
            wrapper_item_id=identity,
        )
    retime = {
        "speedChange": _covered_mapping_value(
            collector, "retime", f"{path}.retime.speedChange", native_speed if native_211 else item_properties,
            "Percentage" if native_211 else "Speed Change", reason="property_not_returned",
        ),
        "retimeProcess": _covered_mapping_value(
            collector, "retime", f"{path}.retime.retimeProcess", item_properties,
            "RetimeProcess" if native_211 else "Retime Process", reason="property_not_returned",
        ),
        "motionEstimation": _covered_mapping_value(
            collector, "retime", f"{path}.retime.motionEstimation", item_properties,
            "MotionEstimation" if native_211 else "Motion Estimation", reason="property_not_returned",
        ),
        "scaling": _covered_mapping_value(
            collector, "retime", f"{path}.retime.scaling", item_properties,
            "Scaling", reason="property_not_returned",
        ),
        "curve": _retime_curve(
            collector, conn, persisted, path, track_type=track_type,
            track_index=track_index,
            item_name=item_name if isinstance(item_name, str) else None,
            identity=identity,
            authoritative_source=authoritative_source,
        ),
        "persistedTimeMapDigest": (
            _covered_mapping_value(
                collector, "retime", f"{path}.retime.persistedTimeMapDigest",
                authoritative_source, "retime_time_map_digest",
                reason="db_readback_unavailable",
            )
        ),
        "sourceAuthority": (
            _covered_mapping_value(
                collector, "retime", f"{path}.retime.sourceAuthority",
                authoritative_source, "retime_source",
                reason="db_readback_unavailable",
            )
        ),
    }
    if native_211:
        retime["nativeSpeed"] = native_speed
    if identity:
        collector.available("items")
    else:
        collector.missing("items", f"{path}.identity", "readback_unavailable", "GetUniqueId")
    video_fade_details = None
    if track_type == "video":
        if isinstance(native_fades, dict) and all(key in native_fades for key in ("FadeIn", "FadeOut")):
            video_fade_details = {
                "fadeInFrames": native_fades["FadeIn"],
                "fadeOutFrames": native_fades["FadeOut"],
                "source": "TimelineItem.GetFades",
                "curve": None,
            }
            if any(native_fades[key] != 0 for key in ("FadeIn", "FadeOut")):
                collector.missing("fades", f"{path}.fades.video.curve", "curve_shape_readback_unavailable")
        elif isinstance(video_fade, dict) and video_fade.get("status") == "available":
            video_fade_details = {
                "fadeInFrames": video_fade.get("fadeInFrames"),
                "fadeOutFrames": video_fade.get("fadeOutFrames"),
                "source": video_fade.get("source"),
                "curve": None,
            }
            collector.available("fades")
            collector.available("fades")
            collector.missing(
                "fades", f"{path}.fades.video.curve",
                "curve_shape_readback_unavailable",
                str(video_fade.get("curveUnavailableReason") or "native video fade curve readback"),
            )
        else:
            collector.missing(
                "fades", f"{path}.fades.video",
                str((video_fade or {}).get("reason") or "project_db_video_fade_readback_unavailable"),
                "Project.db video fade handle readback",
            )
    clip_effects = collector.call(
        "effects", f"{path}.effects.clip", item, "GetClipEffects",
    )
    persisted_audio_effects = (
        _persisted_audio_effects(
            collector, persisted, identity=identity, path=path,
        )
        if track_type == "audio" else None
    )
    revision_evidence = _covered_mapping_value(
        collector,
        "revisions",
        f"{path}.revisionEvidence.inspectorStateDigest",
        authoritative_source,
        "inspector_state_digest",
        reason="db_readback_unavailable",
    )
    linked_identities = None
    linked_getter = getattr(item, "GetLinkedItems", None)
    if not callable(linked_getter):
        collector.missing("items", f"{path}.linkedItemIdentities", "method_unavailable", "GetLinkedItems")
    else:
        try:
            linked = linked_getter()
            if linked is None:
                linked_identities = []
                collector.available("items")
            elif isinstance(linked, (list, tuple)):
                linked_identities = [_item_identity(linked_item) for linked_item in linked]
                if any(value is None for value in linked_identities):
                    collector.missing("items", f"{path}.linkedItemIdentities", "linked_identity_unavailable", "GetLinkedItems/GetUniqueId")
                else:
                    collector.available("items")
            else:
                collector.missing("items", f"{path}.linkedItemIdentities", "invalid_value", "GetLinkedItems")
        except Exception:
            collector.missing("items", f"{path}.linkedItemIdentities", "call_failed", "GetLinkedItems")
    native_state = {}
    if native_211:
        for key, method in (("type", "GetType"), ("outputBlanking", "GetOutputBlanking"),
                            ("useTimelineForOutputBlanking", "GetUseTimelineForOutputBlanking"),
                            ("sourceAudioChannelMapping", "GetSourceAudioChannelMapping")):
            native_state[key] = collector.call("items", f"{path}.native.{key}", item, method)
    return {
        "identity": identity,
        "native": native_state,
        "name": item_name,
        "record": {
            "start": record_start,
            "endExclusive": record_end,
            "duration": record_duration,
        },
        "persistedClassification": persisted_classification,
        "source": {
            "leftOffset": collector.call("items", f"{path}.source.leftOffset", item, "GetLeftOffset"),
            "rightOffset": collector.call("items", f"{path}.source.rightOffset", item, "GetRightOffset"),
            "authoritativeStartFrame": _covered_mapping_value(
                collector, "items", f"{path}.source.authoritativeStartFrame",
                authoritative_source, "source_start_frame",
                reason="authoritative_source_readback_unavailable",
            ),
            "authoritativeEndFrameExclusive": _covered_mapping_value(
                collector, "items", f"{path}.source.authoritativeEndFrameExclusive",
                authoritative_source, "source_end_frame_exclusive",
                reason="authoritative_source_readback_unavailable",
            ),
            "frameRate": _covered_mapping_value(
                collector, "items", f"{path}.source.frameRate",
                authoritative_source, "source_frame_rate",
                reason="authoritative_source_readback_unavailable",
            ),
        },
        "properties": item_properties,
        "enabled": collector.call("items", f"{path}.enabled", item, "GetClipEnabled"),
        "effects": {
            "clip": clip_effects,
            "persistedAudio": persisted_audio_effects,
        },
        "revisionEvidence": {
            "inspectorStateDigest": revision_evidence,
            "source": "Project.db EffectFiltersBA sha256" if revision_evidence else None,
        },
        "markers": collector.call("items", f"{path}.markers", item, "GetMarkers"),
        "flags": collector.call("items", f"{path}.flags", item, "GetFlagList" if native_211 else "GetFlags"),
        "clipColor": collector.call("items", f"{path}.clipColor", item, "GetClipColor"),
        "takes": _takes(collector, item, path),
        "linkedItemIdentities": linked_identities,
        "mediaPoolItem": media_details,
        "fades": {
            "audio": ({"fadeInFrames": native_fades["FadeIn"], "fadeOutFrames": native_fades["FadeOut"], "source": "TimelineItem.GetFades"}
                      if track_type == "audio" and isinstance(native_fades, dict) and all(key in native_fades for key in ("FadeIn", "FadeOut")) else None),
            "video": video_fade_details,
        },
        "keyframes": _keyframes(
            collector, conn, persisted, item, path, track_type=track_type,
            item_name=item_name if isinstance(item_name, str) else None,
            identity=identity,
            track_index=track_index,
            authoritative_source=authoritative_source,
            audio_envelopes_by_id=audio_envelopes_by_id,
            audio_envelope_cache_complete=audio_envelope_cache_complete,
            timeline_resolution=timeline_resolution,
        ),
        "fusion": _fusion(collector, item, path),
        "color": _color(
            collector, item, path, color_primary, color_resolvefx, project=conn.project,
        ) if track_type == "video" else None,
        "fairlight": None,
        "retime": retime,
        "nesting": {
            "kind": nesting_kind,
            "childStructure": nested_structure if nesting_kind == "nested_timeline" else None,
        },
        "multicam": {
            "isMulticam": (
                True
                if nesting_kind == "multicam"
                else False
                if nesting_kind in {"none", "nested_timeline"}
                else None
            ),
            "angleStructure": nested_structure if nesting_kind == "multicam" else None,
        },
    }


def _semantic_source_channel_mapping(
    collector: _Collector, item: dict[str, Any], path: str,
) -> dict[str, Any] | None:
    raw = (item.get("native") or {}).get("sourceAudioChannelMapping")
    if raw is None:
        collector.missing(
            "fairlight", path, "readback_unavailable",
            "TimelineItem.GetSourceAudioChannelMapping",
        )
        return None
    try:
        parsed = native_channel_mapping.parse_timeline_mapping(raw)
        bounded = _bounded_json(parsed)
    except (APICallFailed, TypeError, ValueError):
        collector.missing(
            "fairlight", path, "invalid_native_mapping",
            "TimelineItem.GetSourceAudioChannelMapping",
        )
        return None
    collector.available("fairlight")
    return bounded


def _attach_track_voice_isolation(
    collector: _Collector, conn: Any, fairlight: dict[str, Any],
) -> None:
    for row in fairlight.get("tracks", []):
        if not isinstance(row, dict):
            continue
        index = row.get("track_index")
        path = f"tracks.audio[{index}].fairlight.voiceIsolation"
        try:
            state = timeline_ops.get_timeline_voice_isolation(conn, int(index))
            enabled = state.get("isEnabled")
            amount = state.get("amount")
            if (
                not isinstance(enabled, bool)
                or not isinstance(amount, int)
                or isinstance(amount, bool)
                or not 0 <= amount <= 100
            ):
                raise ValueError
        except Exception:
            row["voiceIsolation"] = None
            collector.missing(
                "fairlight", path, "readback_unavailable",
                "Timeline.GetVoiceIsolationState",
            )
            continue
        row["voiceIsolation"] = {
            "isEnabled": enabled,
            "amount": amount,
            "source": "Timeline.GetVoiceIsolationState",
        }
        collector.available("fairlight")


def _attach_fairlight(collector: _Collector, tracks: list[dict[str, Any]], fairlight: Any) -> None:
    if not isinstance(fairlight, dict):
        collector.missing("fairlight", "fairlight", "readback_unavailable")
        fairlight = {}
    for key, value in fairlight.items():
        if isinstance(value, dict) and value.get("status") == "unavailable":
            collector.missing(
                "fairlight", f"fairlight.{key}",
                str(value.get("reason") or "readback_unavailable"),
            )
    track_rows = {row.get("track_index"): row for row in fairlight.get("tracks", []) if isinstance(row, dict)}
    clip_rows = {
        row.get("item_id"): row
        for row in (fairlight.get("plan_readback") or {}).get("clips", [])
        if isinstance(row, dict) and row.get("item_id")
    }
    for track in tracks:
        if track["type"] != "audio":
            continue
        track["fairlight"] = track_rows.get(track["index"])
        if track["fairlight"] is None:
            collector.missing("fairlight", f"tracks.audio[{track['index']}].fairlight", "readback_unavailable")
        else:
            collector.available("fairlight")
            for key in ("level_db", "pan"):
                control = track["fairlight"].get(key)
                if not isinstance(control, dict) or control.get("status") != "available":
                    collector.missing(
                        "fairlight", f"tracks.audio[{track['index']}].fairlight.{key}",
                        str(control.get("reason") or "readback_unavailable") if isinstance(control, dict) else "readback_unavailable",
                    )
                else:
                    collector.available("fairlight")
        for item_index, item in enumerate(track["items"]):
            saved = clip_rows.get(item.get("identity"))
            item["fairlight"] = dict(saved) if saved is not None else None
            # Live Inspector values are authoritative over the saved project.
            # Both native and persisted pan use the documented -100..100 scale.
            properties = item.get("properties") or {}
            for target, native, enabled in (("gain_db", "AudioVolume", "AudioVolumeEnabled"),
                                             ("pan", "AudioPan", "AudioPanEnabled")):
                value = properties.get(native)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    if item["fairlight"] is None:
                        item["fairlight"] = {"item_id": item.get("identity")}
                    item["fairlight"][target] = value
                    item["fairlight"].setdefault("controlSources", {})[target] = "TimelineItem.GetProperties"
                    if isinstance(properties.get(enabled), bool):
                        item["fairlight"][target + "_enabled"] = properties[enabled]
            mapping_path = f"tracks.audio[{track['index']}].items[{item_index}].fairlight.sourceChannelMapping"
            source_channel_mapping = _semantic_source_channel_mapping(
                collector, item, mapping_path,
            )
            if source_channel_mapping is not None and item["fairlight"] is None:
                item["fairlight"] = {"item_id": item.get("identity")}
            if item["fairlight"] is None:
                item["fairlight"] = {"item_id": item.get("identity")}
                item["fairlight"]["sourceChannelMapping"] = None
                if item["fades"]["audio"] is None:
                    collector.missing("fades", f"tracks.audio[{track['index']}].items[{item_index}].fades.audio", "readback_unavailable")
                collector.missing("fairlight", f"tracks.audio[{track['index']}].items[{item_index}].fairlight", "readback_unavailable")
            else:
                item["fairlight"]["sourceChannelMapping"] = source_channel_mapping
                for key in ("gain_db", "pan", "effect_plugin_ids"):
                    if item["fairlight"].get(key) is None:
                        collector.missing(
                            "fairlight", f"tracks.audio[{track['index']}].items[{item_index}].fairlight.{key}",
                            "persisted_control_not_decoded",
                        )
                if item["fades"]["audio"] is None:
                    item["fades"]["audio"] = {
                        "fadeInFrames": item["fairlight"].get("fade_in_frames"),
                        "fadeOutFrames": item["fairlight"].get("fade_out_frames"),
                    }
                collector.available("fades")
                collector.available("fairlight")


def _audio_fade_coverage(collector: _Collector, tracks: list[dict[str, Any]]) -> None:
    """Account for audio fade semantics even when Fairlight readback fails."""
    reported_paths = {row["path"] for row in collector.unreadable}
    for track in tracks:
        if track["type"] != "audio":
            continue
        for item_index, item in enumerate(track["items"]):
            path = f"tracks.audio[{track['index']}].items[{item_index}].fades.audio"
            fades = item["fades"]["audio"]
            if fades is None:
                if path not in reported_paths:
                    collector.missing("fades", path, "readback_unavailable")
                continue
            for key in ("fadeInFrames", "fadeOutFrames"):
                value = fades.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    fades[key] = None
                    collector.missing("fades", f"{path}.{key}", "readback_unavailable" if value is None else "invalid_value")
            state = item.get("fairlight") or {}
            fades["curve"] = {"in": state.get("fade_in_curve"), "out": state.get("fade_out_curve")}
            for edge, duration in (("in", "fadeInFrames"), ("out", "fadeOutFrames")):
                if fades["curve"][edge] is None and (fades.get(duration) is None or fades[duration] > 0):
                    collector.missing("fades", f"{path}.curve.{edge}", "curve_shape_readback_unavailable")


def _transitions(collector: _Collector, conn: Any, timeline_name: str) -> list[dict[str, Any]] | None:
    rows = edit_insert_overwrite._api_transition_snapshot(conn.timeline)
    method = "DaVinci Resolve Timeline transition API"
    if rows is None:
        try:
            rows = edit_insert_overwrite._db_transition_snapshot(
                conn, {"timeline_name": timeline_name},
            )
            method = "read-only Project.db transition snapshot"
        except Exception:
            collector.missing(
                "transitions", "transitions", "native_and_db_readback_unavailable",
                "Timeline transition API; Project.db transition snapshot",
            )
            return None
    try:
        normalized = _bounded_json(rows)
    except (TypeError, ValueError):
        collector.missing("transitions", "transitions", "invalid_or_unserializable_value", method)
        return None
    collector.available("transitions")
    for index, row in enumerate(normalized):
        if not isinstance(row, dict) or not row.get("transition_id"):
            collector.missing(
                "transitions", f"transitions[{index}].transition_id",
                "native_identity_unavailable", method,
            )
    return normalized


def _track_rows(
    collector: _Collector,
    conn: Any,
    persisted: _PersistedItemReader | None,
    video_fades_by_id: dict[str, dict[str, Any]],
    color_primary_by_id: dict[str, dict[str, Any]],
    color_resolvefx_by_id: dict[str, dict[str, Any]],
    audio_envelopes_by_id: dict[str, dict[str, Any]] | None,
    audio_envelope_cache_complete: bool,
    timeline_resolution: tuple[int, int] | None,
) -> list[dict[str, Any]]:
    timeline = conn.timeline
    tracks: list[dict[str, Any]] = []
    for track_type in ("video", "audio", "subtitle"):
        count = collector.call("tracks", f"tracks.{track_type}.count", timeline, "GetTrackCount", track_type)
        if not isinstance(count, int) or count < 0 or count > 4096:
            if count is not None:
                collector.missing("tracks", f"tracks.{track_type}.count", "invalid_value", "GetTrackCount")
            continue
        for track_index in range(1, count + 1):
            prefix = f"tracks.{track_type}[{track_index}]"
            native_items = []
            getter = getattr(timeline, "GetItemListInTrack", None)
            if not callable(getter):
                collector.missing("items", f"{prefix}.items", "method_unavailable", "GetItemListInTrack")
            else:
                try:
                    native_items = getter(track_type, track_index) or []
                except Exception:
                    collector.missing("items", f"{prefix}.items", "call_failed", "GetItemListInTrack")
            if not isinstance(native_items, (list, tuple)) or len(native_items) > _MAX_COLLECTION:
                collector.missing("items", f"{prefix}.items", "invalid_value", "GetItemListInTrack")
                native_items = []
            else:
                collector.available("items")
            authoritative_by_id: dict[str, dict[str, Any]] = {}
            if track_type in {"video", "audio"}:
                try:
                    authoritative_rows = timeline_ops.get_track_items(
                        conn, track_type, track_index, include_unique_ids=True,
                    )
                    authoritative_by_id = {
                        str(item_row["timeline_item_unique_id"]): item_row
                        for item_row in authoritative_rows
                        if item_row.get("timeline_item_unique_id")
                    }
                except Exception:
                    collector.missing(
                        "retime", f"{prefix}.authoritativeSourceReadback",
                        "db_readback_unavailable", "CutAgent timeline/Project.db readback",
                    )
            row = {
                "type": track_type,
                "index": track_index,
                "name": collector.call("tracks", f"{prefix}.name", timeline, "GetTrackName", track_type, track_index),
                "subtype": collector.call("tracks", f"{prefix}.subtype", timeline, "GetTrackSubType", track_type, track_index),
                "enabled": collector.call("tracks", f"{prefix}.enabled", timeline, "GetIsTrackEnabled", track_type, track_index),
                "locked": collector.call("tracks", f"{prefix}.locked", timeline, "GetIsTrackLocked", track_type, track_index),
                "effects": collector.call("effects", f"{prefix}.effects", timeline, "GetTrackEffects", track_type, track_index),
                "items": [
                    _item_row(
                        collector, conn, persisted, item,
                        track_type=track_type,
                        track_index=track_index,
                        item_index=item_index,
                        authoritative_source=authoritative_by_id.get(str(_item_identity(item))),
                        video_fade=video_fades_by_id.get(str(_item_identity(item))),
                        color_primary=color_primary_by_id.get(str(_item_identity(item))),
                        color_resolvefx=color_resolvefx_by_id.get(str(_item_identity(item))),
                        audio_envelopes_by_id=audio_envelopes_by_id,
                        audio_envelope_cache_complete=audio_envelope_cache_complete,
                        timeline_resolution=timeline_resolution,
                    )
                    for item_index, item in enumerate(native_items)
                ],
            }
            collector.available("tracks")
            tracks.append(row)
    return tracks


def build_timeline_inspection(conn: Any) -> dict[str, Any]:
    from .resolve_api_version import at_least
    from .output_blanking import _preserve_render_context

    if at_least(conn, 21, 1):
        # Detailed inspection reads native blanking directly on every item.
        # Keep one verified render checkpoint for the complete read operation.
        with _preserve_render_context(conn):
            return _build_timeline_inspection(conn)
    return _build_timeline_inspection(conn)


def _build_timeline_inspection(conn: Any) -> dict[str, Any]:
    collector = _Collector()
    from .resolve_api_version import at_least
    collector.item_properties_method = "GetProperties" if at_least(conn, 21, 1) else "GetProperty"
    timeline = conn.timeline
    project = conn.project
    timeline_identity = _item_identity(timeline)
    project_identity = _item_identity(project)
    if timeline_identity:
        collector.available("timeline")
    else:
        collector.missing("timeline", "timeline.identity", "readback_unavailable", "GetUniqueId")
    if project_identity:
        collector.available("timeline")
    else:
        collector.missing("timeline", "project.identity", "readback_unavailable", "GetUniqueId")
    settings = collector.call("timeline", "timeline.settings", timeline, "GetSetting")
    markers = collector.call("timeline", "timeline.markers", timeline, "GetMarkers")
    project_name = collector.call("timeline", "project.name", project, "GetName")
    timeline_name = collector.call("timeline", "timeline.name", timeline, "GetName")
    persisted: _PersistedItemReader | None = None
    try:
        persisted = _PersistedItemReader(conn).__enter__()
    except Exception:
        collector.missing(
            "items", "project.persistedItemSnapshot", "db_readback_unavailable",
            "read-only Project.db snapshot",
        )
    video_fades_by_id: dict[str, dict[str, Any]] = {}
    try:
        video_fade_rows = ([] if collector.item_properties_method == "GetProperties" else
                           video_fade_readback.list_video_fade_handles(conn).get("items") or [])
        video_fades_by_id = {
            str(row["itemId"]): row
            for row in video_fade_rows
            if isinstance(row, dict) and row.get("itemId")
        }
    except Exception:
        collector.missing(
            "fades", "tracks.video.fadeHandles", "db_readback_unavailable",
            "Project.db video fade handle readback",
        )
    color_primary_by_id: dict[str, dict[str, Any]] = {}
    try:
        color_primary_rows = color_primary_readback.list_color_primary_controls(conn).get("items") or []
        color_primary_by_id = {
            str(row["itemId"]): row
            for row in color_primary_rows
            if isinstance(row, dict) and row.get("itemId")
        }
    except Exception:
        collector.missing(
            "color", "tracks.video.colorPrimaryControls", "db_readback_unavailable",
            "Project.db Color primary-control readback",
        )
    color_resolvefx_by_id: dict[str, dict[str, Any]] = {}
    color_resolvefx_scope: dict[str, Any] | None = None
    try:
        resolvefx_state = color_resolvefx_readback.list_color_resolvefx_state(conn)
        color_resolvefx_by_id = {
            str(row["itemId"]): row
            for row in resolvefx_state.get("items") or []
            if isinstance(row, dict) and row.get("itemId")
        }
        color_resolvefx_scope = {
            "knownNodeStackLayers": resolvefx_state.get("knownNodeStackLayers") or [],
            "unknownRemainder": resolvefx_state.get("unknownRemainder") or [],
            "identitySource": resolvefx_state.get("identitySource"),
            "route": resolvefx_state.get("route"),
        }
        for index, row in enumerate(color_resolvefx_scope["unknownRemainder"]):
            collector.missing(
                "color", f"color.resolveFx.unknownRemainder[{index}].{row.get('scope') or 'scope'}",
                str(row.get("reason") or "resolvefx_scope_unavailable"),
                "strict persisted ResolveFX readback",
            )
    except Exception:
        collector.missing(
            "color", "tracks.video.colorResolveFx", "db_readback_unavailable",
            "exact persisted ResolveFX readback",
        )
    audio_envelopes_by_id: dict[str, dict[str, Any]] | None = None
    audio_envelope_cache_complete = False
    try:
        audio_envelope_state = keyframe_db.list_audio_volume_envelopes(
            conn, limit=_MAX_COLLECTION,
        )
        audio_envelopes = audio_envelope_state.get("envelopes") or []
        audio_envelopes_by_id = {
            str((row.get("clip") or {})["item_id"]): row
            for row in audio_envelopes
            if isinstance(row, dict) and (row.get("clip") or {}).get("item_id")
        }
        audio_envelope_cache_complete = not bool(audio_envelope_state.get("truncated"))
    except Exception:
        pass
    timeline_resolution: tuple[int, int] | None = None
    try:
        timeline_resolution = keyframe_db._timeline_resolution(conn)
    except Exception:
        pass
    timeline_output = None
    try:
        if persisted is None:
            raise LookupError("Persisted reader unavailable")
        timeline_output = persisted.timeline_output(timeline_identity)
        collector.available("fairlight")
    except Exception:
        collector.missing("fairlight", "fairlight.timelineOutput", "exact_persisted_output_unavailable", "identity-bound sequence output readback")
    try:
        tracks = _track_rows(
            collector, conn, persisted, video_fades_by_id, color_primary_by_id,
            color_resolvefx_by_id, audio_envelopes_by_id,
            audio_envelope_cache_complete, timeline_resolution,
        )
    finally:
        if persisted is not None:
            persisted.close()

    transitions = _transitions(
        collector, conn, timeline_name if isinstance(timeline_name, str) else "",
    )
    try:
        fairlight = timeline_ops._inspect_sdk_fairlight_state(conn)
    except Exception:
        fairlight = None
        collector.missing("fairlight", "fairlight", "call_failed", "CutAgent Fairlight readback")
    if isinstance(fairlight, dict):
        _attach_track_voice_isolation(collector, conn, fairlight)
        fairlight["timelineOutput"] = timeline_output
        # The verified read model below covers track controls and exact clip
        # carriers. It does not currently bind automation or routing topology,
        # so those requested domains must remain explicit gaps.
        fairlight["automation"] = {
            "status": "unavailable",
            "reason": "not_exposed_by_verified_readback",
        }
        fairlight["routing"] = {
            "status": "unavailable",
            "reason": "not_exposed_by_verified_readback",
        }
        try:
            bus_labels = fairlight_ops.read_fairlight_bus_list_db(conn)
            fairlight["busLabelEvidence"] = {
                "mainOutputs": bus_labels.get("main_outputs") or [],
                "buses": bus_labels.get("buses") or [],
                "readScope": "labels_only",
                "activeTopologyProven": False,
            }
            collector.available("fairlight")
        except Exception:
            fairlight["busLabelEvidence"] = None
            collector.missing(
                "fairlight", "fairlight.busLabelEvidence", "db_readback_unavailable",
                "Fairlight Project.db label-token readback",
            )
        try:
            fairlight = _bounded_json(fairlight)
        except (TypeError, ValueError):
            fairlight = None
            collector.missing(
                "fairlight", "fairlight", "invalid_or_unserializable_value",
                "CutAgent Fairlight readback",
            )
    _attach_fairlight(collector, tracks, fairlight)
    _audio_fade_coverage(collector, tracks)
    project_row = {
        "identity": project_identity,
        "name": project_name,
    }
    timeline_row = {
        "identity": timeline_identity,
        "name": timeline_name,
        "startFrame": collector.call("timeline", "timeline.startFrame", timeline, "GetStartFrame"),
        "endFrame": collector.call("timeline", "timeline.endFrame", timeline, "GetEndFrame"),
        "startTimecode": collector.call("timeline", "timeline.startTimecode", timeline, "GetStartTimecode"),
        "currentTimecode": collector.call("timeline", "timeline.currentTimecode", timeline, "GetCurrentTimecode"),
        "settings": settings,
        "markers": markers,
        "colorGraph": _native_color_graph(collector, timeline, "GetNodeGraph", "timeline.colorGraph"),
    }
    if collector.item_properties_method == "GetProperties":
        timeline_row["outputBlanking"] = collector.call("timeline", "timeline.outputBlanking", timeline, "GetOutputBlanking")
    revision_payload = _bounded_json({
        "projectIdentity": project_identity,
        "timelineIdentity": timeline_identity,
        "timeline": timeline_row,
        "tracks": tracks,
        "transitions": transitions,
        "fairlight": fairlight,
    })
    timeline_row["revisionEvidence"] = {
        "kind": "inspection_document_sha256",
        "sha256": hashlib.sha256(
            json.dumps(revision_payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest(),
        "nativeRevisionToken": None,
    }
    collector.available("revisions")
    collector.missing(
        "revisions", "timeline.revisionEvidence.nativeRevisionToken",
        "not_exposed_by_runtime",
    )
    return {
        "schema": SCHEMA,
        "purpose": "inspection_only",
        "reconstructable": False,
        "scope": {
            "trigger": "explicit_on_demand_export",
            "automaticStartupOrMessageExport": False,
            "requestedDomains": list(REQUESTED_DOMAINS),
        },
        "snapshotConsistency": {
            "mode": "mixed_live_and_independently_sampled_persisted_state",
            "liveReadback": "DaVinci Resolve scripting and Fusion APIs at export time",
            "persistedReadback": "independent read-only Project.db transactions sampled at last saved or autosaved state",
            "persistedCrossReaderAtomicityVerified": False,
            "unsavedGuiEqualityVerified": False,
            "automaticSavePerformed": False,
        },
        "colorResolveFxReadback": color_resolvefx_scope,
        "project": project_row,
        "timeline": timeline_row,
        "tracks": tracks,
        "transitions": transitions,
        "fairlight": fairlight,
        "coverage": collector.report(),
    }


def write_timeline_inspection(conn: Any, output_path: str, *, force: bool = False) -> dict[str, Any]:
    requested = Path(output_path).expanduser()
    if requested.is_symlink():
        raise ValidationError("Timeline inspection export destination must not be a symbolic link.")
    destination = requested.resolve(strict=False)
    if destination.suffix.lower() != ".json":
        raise ValidationError("Timeline inspection export path must end in .json.")
    if not destination.parent.is_dir():
        raise ValidationError("Timeline inspection export parent directory does not exist.")
    if destination.exists() and not force:
        raise ValidationError("Timeline inspection export already exists. Use --force to replace it.")
    if destination.exists() and not destination.is_file():
        raise ValidationError("Timeline inspection export destination is not a regular file.")

    document = build_timeline_inspection(conn)
    encoded = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
    except OSError as exc:
        raise APICallFailed("Failed to write the timeline inspection export.") from exc
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
    return {
        "path": str(destination),
        "schema": SCHEMA,
        "byte_count": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "complete": document["coverage"]["complete"],
        "unreadable_field_count": document["coverage"]["unreadableFieldCount"],
        "domain_status": {
            domain: detail["status"]
            for domain, detail in document["coverage"]["domains"].items()
        },
    }


__all__ = ["SCHEMA", "build_timeline_inspection", "write_timeline_inspection"]
