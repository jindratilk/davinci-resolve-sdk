"""Carrier-admitted Fairlight execution inside the proprietary CLI wheel.

The reviewed handler mapping and result projection remain private to CutAgent
CLI. A handler return is never proof: live bindings, independent verification,
and schema-valid semantic results must agree before success is published.
"""

from __future__ import annotations

import json
import hashlib
import inspect
import math
import os
import re
import threading
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import click
from typer.models import ArgumentInfo, OptionInfo

from ._sdk_prepared_action_contract import PREPARED_ACTION_ACTION_METADATA
from ._sdk_prepared_action_contract import PREPARED_ACTION_MAX_RESULT_BYTES
from .sdk_prepared_action import prepared_action_digest

_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_STAGES = frozenset({"prepare", "current", "verify", "project", "recover"})
_HANDLER_LOCK = threading.RLock()
_HANDLERS = {
    action_id: action_id.removeprefix("cutagent.action.fairlight.").replace(".", "_")
    for action_id in PREPARED_ACTION_ACTION_METADATA
    if action_id.startswith("cutagent.action.fairlight.")
}
_HANDLERS.update(
    {
        "cutagent.action.fairlight.add": "add_track",
        "cutagent.action.fairlight.delete": "delete_track",
        "cutagent.action.fairlight.insert": "insert_audio",
    }
)
_ARTIFACT_FIELDS = frozenset(
    {"outputPath", "mediaPath", "path", "folder", "sourcePath", "filePath"}
)
_CLIP_PREFIXES = (
    "cutagent.action.fairlight.ai.",
    "cutagent.action.fairlight.clip.",
    "cutagent.action.fairlight.elastic.",
    "cutagent.action.fairlight.eq.",
    "cutagent.action.fairlight.item_source.",
    "cutagent.action.fairlight.transition.",
)
_CREATE_ACTION_IDS = frozenset(
    {
        "cutagent.action.fairlight.add",
        "cutagent.action.fairlight.clip.split",
        "cutagent.action.fairlight.effect.add",
        "cutagent.action.fairlight.ensure_stereo_tracks",
        "cutagent.action.fairlight.ensure_tracks",
        "cutagent.action.fairlight.insert",
        "cutagent.action.fairlight.sound_library.index_file",
        "cutagent.action.fairlight.sound_library.index_folder",
        "cutagent.action.fairlight.sound_library.insert",
        "cutagent.action.fairlight.track.duplicate",
        "cutagent.action.fairlight.transition.add",
    }
)
_POST_MUTATION_AUDITION_ACTION_IDS = frozenset(
    {
        "cutagent.action.fairlight.insert",
        "cutagent.action.fairlight.sound_library.insert",
    }
)
_DELETE_ACTION_IDS = frozenset(
    {
        "cutagent.action.fairlight.clip.delete",
        "cutagent.action.fairlight.delete",
        "cutagent.action.fairlight.effect.remove",
        "cutagent.action.fairlight.sound_library.delete",
        "cutagent.action.fairlight.sound_library.source_remove",
    }
)
_BROAD_ACTION_IDS = frozenset(
    {
        "cutagent.action.fairlight.clip.link",
        "cutagent.action.fairlight.ensure_stereo_tracks",
        "cutagent.action.fairlight.ensure_tracks",
    }
)

_FAIRLIGHT_READ_ACTION_IDS = frozenset(
    {
        "cutagent.action.fairlight.channel_map.clip",
        "cutagent.action.fairlight.clip.linked.list",
        "cutagent.action.fairlight.clip.source_range",
        "cutagent.action.fairlight.clip.track_info",
        "cutagent.action.fairlight.sound_library.list",
        "cutagent.action.fairlight.sound_library.search",
        "cutagent.action.fairlight.sound_library.source_list",
    }
)
_ID_PART = re.compile(r"[^A-Za-z0-9._~-]+")


class FairlightEvaluationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@lru_cache(maxsize=1)
def _contracts() -> Mapping[str, Any]:
    path = (
        Path(__file__).resolve().parent
        / "public_contract"
        / "action-contracts.schema.json"
    )
    value = json.loads(path.read_text(encoding="utf-8")).get("$defs")
    if not isinstance(value, Mapping):
        raise RuntimeError("Fairlight action contracts are unavailable.")
    return value


def _schema(action_id: str, kind: str) -> Mapping[str, Any]:
    value = _contracts().get(f"{action_id}.{kind}")
    if not isinstance(value, Mapping):
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", f"Fairlight {kind} contract is unavailable."
        )
    return value


def _validate(value: Any, schema: Mapping[str, Any] | bool, path: str) -> None:
    if schema is True:
        return
    if schema is False:
        raise FairlightEvaluationError("VALIDATION_ERROR", f"{path} is unavailable.")
    if "$ref" in schema:
        prefix = "#/$defs/"
        reference = schema["$ref"]
        if not isinstance(reference, str) or not reference.startswith(prefix):
            raise RuntimeError("Fairlight contract reference is not local.")
        _validate(value, _contracts()[reference[len(prefix) :]], path)
        return
    for part in schema.get("allOf", ()):
        _validate(value, part, path)
    if "if" in schema:
        try:
            _validate(value, schema["if"], path)
        except FairlightEvaluationError:
            branch = schema.get("else")
        else:
            branch = schema.get("then")
        if branch is not None:
            _validate(value, branch, path)
    if "oneOf" in schema:
        matches = 0
        for part in schema["oneOf"]:
            try:
                _validate(value, part, path)
            except FairlightEvaluationError:
                continue
            matches += 1
        if matches != 1:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", f"{path} must match one contract branch."
            )
        return
    if "anyOf" in schema:
        for part in schema["anyOf"]:
            try:
                _validate(value, part, path)
                break
            except FairlightEvaluationError:
                continue
        else:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", f"{path} matches no contract branch."
            )
        return
    if "const" in schema and value != schema["const"]:
        raise FairlightEvaluationError("VALIDATION_ERROR", f"{path} constant differs.")
    expected = schema.get("type")
    types = expected if isinstance(expected, list) else [expected]
    valid = expected is None or any(
        (item == "null" and value is None)
        or (item == "object" and isinstance(value, Mapping))
        or (item == "array" and isinstance(value, list))
        or (item == "string" and isinstance(value, str))
        or (item == "boolean" and isinstance(value, bool))
        or (
            item == "integer" and isinstance(value, int) and not isinstance(value, bool)
        )
        or (
            item == "number"
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
        for item in types
    )
    if not valid:
        raise FairlightEvaluationError("VALIDATION_ERROR", f"{path} type differs.")
    if "enum" in schema and value not in schema["enum"]:
        raise FairlightEvaluationError("VALIDATION_ERROR", f"{path} value is invalid.")
    if isinstance(value, Mapping):
        properties = schema.get("properties", {})
        required = set(schema.get("required", ()))
        if not required <= set(value) or (
            schema.get("additionalProperties") is False and set(value) - set(properties)
        ):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", f"{path} violates its closed contract."
            )
        for key, item in value.items():
            if key in properties:
                _validate(item, properties[key], f"{path}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get(
            "maxItems", 1_000_000
        ):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", f"{path} length is invalid."
            )
        if schema.get("uniqueItems") and len(
            {json.dumps(item, sort_keys=True) for item in value}
        ) != len(value):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", f"{path} must be unique."
            )
        for index, item in enumerate(value):
            if "items" in schema:
                _validate(item, schema["items"], f"{path}[{index}]")
        if "contains" in schema and not any(
            _matches(item, schema["contains"], f"{path}[{index}]")
            for index, item in enumerate(value)
        ):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", f"{path} lacks required evidence."
            )
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get(
            "maxLength", 1_000_000
        ):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", f"{path} length is invalid."
            )
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", f"{path} format is invalid."
            )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", -math.inf) or value > schema.get(
            "maximum", math.inf
        ):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", f"{path} range is invalid."
            )
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", f"{path} range is invalid."
            )
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", f"{path} range is invalid."
            )


def _matches(value: Any, schema: Mapping[str, Any] | bool, path: str) -> bool:
    try:
        _validate(value, schema, path)
    except FairlightEvaluationError:
        return False
    return True


def _canonical(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _read_evidence(summary: str) -> dict[str, Any]:
    return {
        "checks": [
            {"kind": "structural_readback", "status": "passed", "summary": summary}
        ],
        "audition": {"required": False, "status": "not_run"},
    }


def _read_clip(prepared: Mapping[str, Any]) -> Mapping[str, Any]:
    snapshot = prepared.get("preState", {}).get("snapshot")
    clip = snapshot.get("clip") if isinstance(snapshot, Mapping) else None
    if not isinstance(clip, Mapping):
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Exact Fairlight clip pre-state is unavailable."
        )
    return clip


def _library_item(item: Mapping[str, Any]) -> dict[str, Any]:
    file_info = item.get("file") if isinstance(item.get("file"), Mapping) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    raw_id = str(item.get("clip_id") or file_info.get("file_id") or "unknown")
    stable_id = _ID_PART.sub("_", raw_id).strip("_") or "unknown"
    tags: list[str] = []
    for candidate in (
        item.get("category"),
        metadata.get("user1"),
        metadata.get("user2"),
        metadata.get("user3"),
        metadata.get("user4"),
    ):
        if isinstance(candidate, str) and candidate and candidate not in tags:
            tags.append(candidate)
    path = file_info.get("path")
    name = item.get("name") or item.get("filename") or file_info.get("filename")
    duration_samples = int(file_info.get("duration") or item.get("duration") or 0)
    sample_rate = int(file_info.get("sample_rate") or 0)
    frame_rate = float(file_info.get("frame_rate") or 0.0)
    if (
        not isinstance(path, str)
        or not path
        or not isinstance(name, str)
        or not name
        or duration_samples < 0
        or sample_rate <= 0
        or frame_rate <= 0
    ):
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Sound Library item identity is incomplete."
        )
    return {
        "libraryItemId": f"library_item_{stable_id}",
        "name": name,
        "path": path,
        "durationFrames": int(round((duration_samples / sample_rate) * frame_rate)),
        "sampleRate": sample_rate,
        "channelCount": int(file_info["channel_count"])
        if file_info.get("channel_count")
        else None,
        "tags": tags,
    }


def _project_read_result(
    action_id: str, prepared: Mapping[str, Any], raw: Any
) -> dict[str, Any]:
    if isinstance(raw, Mapping) and isinstance(raw.get("handlerResult"), Mapping):
        raw = raw["handlerResult"]
    if not isinstance(raw, Mapping):
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Fairlight readback is not an object."
        )
    command_id = action_id.removeprefix("cutagent.action.")
    if command_id == "fairlight.channel_map.clip":
        mapping = raw.get("mapping")
        tracks = mapping.get("track_mapping") if isinstance(mapping, Mapping) else None
        if not isinstance(tracks, Mapping):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Channel mapping readback is incomplete."
            )
        channels = [
            {
                "sourceChannel": int(source),
                "destinationChannel": int(destination),
                "enabled": not bool(record.get("mute", False)),
            }
            for destination, record in sorted(
                tracks.items(), key=lambda item: str(item[0])
            )
            if isinstance(record, Mapping)
            for source in record.get("channel_idx", ())
        ]
        projected = {
            "actionId": action_id,
            "mapping": {
                "clip": _read_clip(prepared),
                "channels": {"channelCount": len(channels), "channels": channels},
            },
            "affectedCount": 0,
            "evidence": _read_evidence(
                "Exact timeline-item channel mapping read back."
            ),
        }
    elif command_id == "fairlight.clip.linked.list":
        linked = raw.get("linked")
        if not isinstance(linked, list):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Linked-item readback is incomplete."
            )
        projected = {
            "actionId": action_id,
            "links": {
                "clipName": str(
                    raw.get("clip") or _read_clip(prepared).get("clipName") or ""
                ),
                "items": [
                    {
                        "clipName": str(item.get("name") or ""),
                        "recordStartFrame": item.get("start"),
                        "recordEndFrame": item.get("end"),
                    }
                    for item in linked
                    if isinstance(item, Mapping)
                ],
            },
        }
    elif command_id == "fairlight.clip.source_range":
        names = {
            "start": "recordStartFrame",
            "end": "recordEndFrame",
            "duration": "durationFrames",
            "left_offset": "leftOffsetFrames",
            "right_offset": "rightOffsetFrames",
            "source_start": "sourceStartFrame",
            "source_end": "sourceEndFrame",
        }
        value = {
            "clipName": str(
                raw.get("clip") or _read_clip(prepared).get("clipName") or ""
            )
        }
        value.update(
            {
                target: int(raw[source])
                for source, target in names.items()
                if raw.get(source) is not None
            }
        )
        projected = {"actionId": action_id, "range": value}
    elif command_id == "fairlight.clip.track_info":
        projected = {
            "actionId": action_id,
            "trackBinding": {
                "clipName": str(
                    raw.get("clip") or _read_clip(prepared).get("clipName") or ""
                ),
                "trackType": raw.get("track_type"),
                "trackIndex": raw.get("track_index"),
            },
        }
    elif command_id in {
        "fairlight.sound_library.list",
        "fairlight.sound_library.search",
    }:
        items = raw.get("results")
        if not isinstance(items, list):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Sound Library readback is incomplete."
            )
        field = "library" if command_id.endswith(".list") else "matches"
        body: dict[str, Any] = {
            "scope": raw.get("database"),
            "items": [
                _library_item(item) for item in items if isinstance(item, Mapping)
            ],
        }
        if field == "matches":
            body["query"] = raw.get("query")
        projected = {
            "actionId": action_id,
            field: body,
            "affectedCount": 0,
            "evidence": _read_evidence("Bounded Sound Library rows read back."),
        }
    else:
        sources = raw.get("sources")
        if not isinstance(sources, list):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Sound Library source readback is incomplete."
            )
        recursive = bool(prepared["lowering"]["normalizedInput"].get("recursive", True))
        projected = {
            "actionId": action_id,
            "sources": {
                "scope": raw.get("database"),
                "entries": [
                    {
                        "path": item.get("path"),
                        "recursive": recursive,
                        "indexedFileCount": int(item.get("file_count") or 0),
                    }
                    for item in sources
                    if isinstance(item, Mapping)
                ],
            },
            "affectedCount": 0,
            "evidence": _read_evidence("Bounded Sound Library sources read back."),
        }
    _validate(projected, _schema(action_id, "result"), "result")
    return _canonical(projected)


def _callback(
    authority: "FairlightEvaluationExecutionAuthority",
    context: Mapping[str, Any],
    action_id: str,
    phase: str,
    payload: Mapping[str, Any],
    *,
    target_kinds: list[str] | None = None,
) -> Mapping[str, Any]:
    if phase not in _STAGES:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "Fairlight phase is invalid."
        )
    callback = authority.live_target_resolver()
    request = context.get("exactRequestBinding")
    if not isinstance(request, Mapping) or request.get("actionId") != action_id:
        raise FairlightEvaluationError(
            "STALE_REVISION", "Fairlight signed request binding is unavailable."
        )
    identities = request.get("identities")
    revisions = request.get("revisions")
    target_ids = (
        identities.get("targetIds") if isinstance(identities, Mapping) else None
    )
    target_revisions = (
        revisions.get("targets") if isinstance(revisions, Mapping) else None
    )
    if not isinstance(target_ids, (list, tuple)) or not isinstance(
        target_revisions, Mapping
    ):
        raise FairlightEvaluationError(
            "STALE_REVISION", "Fairlight target binding is unavailable."
        )
    if target_kinds is None:
        private_bindings = context.get("privateBindings")
        fairlight_binding = (
            private_bindings.get("fairlight")
            if isinstance(private_bindings, Mapping)
            else None
        )
        private_targets = (
            fairlight_binding.get("targets")
            if isinstance(fairlight_binding, Mapping)
            else None
        )
        if isinstance(private_targets, (list, tuple)) and len(private_targets) == len(
            target_ids
        ):
            target_kinds = [
                target.get("kind") if isinstance(target, Mapping) else None
                for target in private_targets
            ]
        else:
            target_kinds = _carrier_target_kinds(action_id, len(target_ids))
    else:
        target_kinds = list(target_kinds)
    if len(target_kinds) != len(target_ids) or any(
        kind not in {"project", "timeline", "track", "clip", "media", "marker"}
        for kind in target_kinds
    ):
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "Fairlight target-kind binding is invalid."
        )
    scope = {
        "projectId": identities.get("projectId"),
        "timelineId": identities.get("timelineId"),
        "projectRevision": revisions.get("project"),
        "timelineRevision": revisions.get("timeline"),
    }
    response = callback(
        _canonical(
            {
                "contractVersion": 1,
                "phase": phase,
                "actionId": action_id,
                "operationId": context.get("operationId"),
                "executionId": context.get("executionId"),
                "scope": scope,
                "targets": [
                    {
                        "kind": kind,
                        "stableId": target_id,
                        "revision": target_revisions.get(target_id),
                    }
                    for kind, target_id in zip(target_kinds, target_ids, strict=True)
                ],
                "targetRequirements": target_kinds,
                "requiredEvidence": _required_evidence(action_id),
                **dict(payload),
            }
        )
    )
    response_scope = response.get("scope") if isinstance(response, Mapping) else None
    if (
        not isinstance(response, Mapping)
        or response.get("contractVersion") != 1
        or response.get("actionId") != action_id
        or response.get("phase") != phase
        or not isinstance(response_scope, Mapping)
        or any(response_scope.get(key) != value for key, value in scope.items())
    ):
        raise FairlightEvaluationError(
            "RUNTIME_UNAVAILABLE", "Fairlight live carrier response is invalid."
        )
    return response


def _targets(
    context: Mapping[str, Any], response: Mapping[str, Any]
) -> list[dict[str, Any]]:
    request = context["exactRequestBinding"]
    identities = request.get("identities", {})
    revisions = request.get("revisions", {})
    expected_ids = identities.get("targetIds")
    expected_revisions = revisions.get("targets")
    targets = response.get("targets")
    if (
        not isinstance(expected_ids, (list, tuple))
        or not isinstance(expected_revisions, Mapping)
        or not isinstance(targets, (list, tuple))
        or len(targets) != len(expected_ids)
    ):
        raise FairlightEvaluationError(
            "STALE_REVISION", "Fairlight target set is incomplete."
        )
    normalized = []
    for target, target_id in zip(targets, expected_ids, strict=True):
        if (
            not isinstance(target, Mapping)
            or target.get("stableId") != target_id
            or target.get("revision") != expected_revisions.get(target_id)
            or not isinstance(target.get("kind"), str)
            or not target["kind"]
        ):
            raise FairlightEvaluationError(
                "STALE_REVISION",
                "Fairlight live target differs from the signed carrier.",
            )
        normalized.append(
            _canonical(
                {
                    "kind": target["kind"],
                    "stableId": target_id,
                    "revision": expected_revisions[target_id],
                    "projectId": identities.get("projectId"),
                    "timelineId": identities.get("timelineId"),
                }
            )
        )
    return normalized


def _carrier_target_kinds(
    action_id: str, count: int, value: Mapping[str, Any] | None = None
) -> list[str]:
    if count < 1:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "Fairlight target set is empty."
        )
    if action_id.startswith(_CLIP_PREFIXES) or action_id in {
        "cutagent.action.fairlight.channel_map.clip",
        "cutagent.action.fairlight.channel_map.set",
    }:
        return ["clip"] * count
    if action_id in {
        "cutagent.action.fairlight.effect.add",
        "cutagent.action.fairlight.effect.remove",
    }:
        expected = 2 if isinstance(value, Mapping) and value.get("clip") else 1
        if count != expected:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Fairlight effect target set is incomplete."
            )
        return ["timeline", *(["clip"] if count == 2 else [])]
    if action_id == "cutagent.action.fairlight.effect.set_param":
        return ["clip"] * count
    if action_id == "cutagent.action.fairlight.automation.write":
        return [
            "timeline" if isinstance(value, Mapping) and value.get("bus") else "track"
        ] * count
    if action_id in {
        "cutagent.action.fairlight.bounce.mix_to_track",
        "cutagent.action.fairlight.bounce.track",
    }:
        if count != 3:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Fairlight bounce target set is incomplete."
            )
        return ["track", "track", "clip"]
    if action_id == "cutagent.action.fairlight.delete":
        return ["track", *(["clip"] * (count - 1))]
    if action_id == "cutagent.action.fairlight.track.duplicate":
        if count < 2:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Fairlight duplicate target set is incomplete."
            )
        return ["track", "track", *(["clip"] * (count - 2))]
    if action_id == "cutagent.action.fairlight.sound_library.insert":
        if count != 3:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Fairlight library insert target set is incomplete."
            )
        return ["project", "track", "clip"]
    if action_id.startswith("cutagent.action.fairlight.sound_library."):
        return ["project"] * count
    if action_id in {
        "cutagent.action.fairlight.export.audio",
        "cutagent.action.fairlight.preset.apply",
    }:
        return ["timeline", *(["track"] * (count - 1))]
    if action_id == "cutagent.action.fairlight.insert":
        return ["track", *(["clip"] * (count - 1))]
    return ["track"] * count


def _required_evidence(action_id: str) -> list[str]:
    metadata = PREPARED_ACTION_ACTION_METADATA[action_id]
    if metadata["operationClass"] == "read":
        return ["structural_readback"]
    evidence = ["structural_readback"]
    evidence.append("protected_state_readback")
    if action_id == "cutagent.action.fairlight.export.audio":
        evidence.append("artifact_validation")
    return evidence


def _required_modalities(
    action_id: str, *, audition_required: bool = False
) -> list[str]:
    if PREPARED_ACTION_ACTION_METADATA[action_id]["operationClass"] == "read":
        return ["structural"]
    modalities = ["readback", "structural"]
    if audition_required:
        modalities.append("auditioned")
    if action_id == "cutagent.action.fairlight.export.audio":
        modalities.append("file")
    return modalities


def _managed_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "Fairlight managed path is invalid."
        )
    candidate = Path(value).expanduser().resolve(strict=False)
    roots = [
        Path(root).expanduser().resolve(strict=False)
        for name in ("CUTAGENT_USER_UPLOADS_DIR", "CUTAGENT_USER_EXPORTS_DIR")
        if (root := os.environ.get(name))
    ]
    if (
        not candidate.is_absolute()
        or not roots
        or not any(candidate == root or root in candidate.parents for root in roots)
    ):
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "Fairlight path is outside managed runtime custody."
        )
    return str(candidate)


def _capture_artifact_baselines(
    action_id: str, value: Mapping[str, Any]
) -> dict[str, Any]:
    from .fairlight_runtime_artifacts import capture_fairlight_artifact_identity

    command_id = action_id.removeprefix("cutagent.action.")
    baselines: dict[str, Any] = {}
    for field, item in value.items():
        if field not in _ARTIFACT_FIELDS or not isinstance(item, str):
            continue
        captured = capture_fairlight_artifact_identity(command_id, field, item)
        if captured is not None:
            baselines[field] = captured
    if (
        command_id
        in {
            "fairlight.export.audio",
            "fairlight.bounce.mix_to_track",
            "fairlight.bounce.track",
        }
        and "outputPath" not in baselines
    ):
        raise FairlightEvaluationError(
            "VALIDATION_ERROR",
            "Fairlight rendered-audio actions require an explicit managed outputPath.",
        )
    return baselines


def _validate_fresh_artifacts(prepared: Mapping[str, Any]) -> dict[str, Any]:
    from .fairlight_runtime_artifacts import validate_fresh_fairlight_artifact

    baselines = prepared.get("preState", {}).get("artifactBaselines", {})
    if not isinstance(baselines, Mapping):
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Fairlight artifact baselines are unavailable."
        )
    return {
        field: validate_fresh_fairlight_artifact(dict(baseline), baseline["path"])
        for field, baseline in baselines.items()
    }


def _default(parameter: inspect.Parameter) -> Any:
    value = parameter.default
    if isinstance(value, (ArgumentInfo, OptionInfo)):
        value = value.default
    if value is inspect.Parameter.empty or value is ...:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", f"Missing Fairlight input: {parameter.name}."
        )
    return deepcopy(value)


def _prepare_lowering(
    action_id: str, value: Mapping[str, Any], overrides: Mapping[str, Any]
) -> dict[str, Any]:
    from .commands import fairlight as commands

    handler_name = _HANDLERS.get(action_id)
    handler = getattr(commands, handler_name or "", None)
    if not callable(handler):
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Reviewed Fairlight handler is unavailable.",
        )
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__
    signature = inspect.signature(handler)
    kwargs = {}
    for name, parameter in signature.parameters.items():
        if name == "ctx":
            continue
        try:
            kwargs[name] = _default(parameter)
        except FairlightEvaluationError:
            pass
    for field, item in value.items():
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", field).lower()
        if field == "libraryScope":
            name = "database"
        elif field == "timelineName" and action_id.endswith("ensure_stereo_tracks"):
            name = "timeline"
        if field in _ARTIFACT_FIELDS:
            item = _managed_path(item)
        if name in signature.parameters:
            kwargs[name] = (
                json.dumps(item, separators=(",", ":"))
                if field == "bands" and not isinstance(item, str)
                else item
            )
    if action_id == "cutagent.action.fairlight.channel_map.set":
        channels = value.get("channels")
        if not isinstance(channels, list):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Fairlight channel mapping is invalid."
            )
        source_channels = [
            row.get("sourceChannel") for row in channels if isinstance(row, Mapping)
        ]
        if (
            len(source_channels) != len(channels)
            or source_channels not in ([1], [2], [1, 2])
            or any(
                row.get("destinationChannel") != 1 or row.get("enabled") is not True
                for row in channels
            )
        ):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR",
                "Fairlight channel mapping supports the verified stereo source mappings [1], [2], or [1, 2].",
            )
        kwargs["mapping_json"] = json.dumps(
            {
                "track_mapping": {
                    "1": {
                        "channel_idx": source_channels,
                        "mute": False,
                        "type": "stereo",
                    }
                },
                "embedded_audio_channels": 2,
                "linked_audio": {},
            },
            separators=(",", ":"),
        )
    elif action_id == "cutagent.action.fairlight.solo_restore":
        states = value.get("trackStates")
        if not isinstance(states, list):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Fairlight track restore state is invalid."
            )
        indices = [row.get("trackIndex") for row in states if isinstance(row, Mapping)]
        if len(indices) != len(states) or len(set(indices)) != len(indices):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR",
                "Fairlight track restore state contains duplicate or invalid tracks.",
            )
        kwargs["states_json"] = json.dumps(
            [{"index": row["trackIndex"], "enabled": row["enabled"]} for row in states],
            separators=(",", ":"),
        )
    allowed_parameters = set(signature.parameters) - {"ctx"}
    if not isinstance(overrides, Mapping) or set(overrides) - allowed_parameters:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "Fairlight live overrides are invalid."
        )
    kwargs.update(deepcopy(dict(overrides)))
    if (
        action_id == "cutagent.action.fairlight.item_source.patch"
        and kwargs.get("item_id") is not None
    ):
        # The public record selectors are capture-time assertions for the stable
        # item identity. The native command accepts either that identity or the
        # legacy track/frame selector family, never both.
        for selector in (
            "track_index",
            "record_frame",
            "record_duration",
            "record_end",
        ):
            kwargs[selector] = None
    missing = allowed_parameters - set(kwargs)
    if missing:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR",
            "Missing Fairlight input: " + ", ".join(sorted(missing)) + ".",
        )
    if action_id == "cutagent.action.fairlight.delete":
        kwargs["force"] = True
    return {"handlerName": handler_name, "kwargs": kwargs}


def _derived_overrides(
    action_id: str,
    response: Mapping[str, Any],
    value: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from .commands import fairlight as commands

    handler_name = _HANDLERS.get(action_id)
    handler = getattr(commands, handler_name or "", None)
    while callable(handler) and hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__
    if not callable(handler):
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Reviewed Fairlight handler is unavailable.",
        )
    parameters = set(inspect.signature(handler).parameters)
    rows = response.get("targets")
    if not isinstance(rows, (list, tuple)) or not rows:
        raise FairlightEvaluationError(
            "STALE_REVISION", "Fairlight live locators are unavailable."
        )
    clip_rows = [
        row for row in rows if isinstance(row, Mapping) and row.get("kind") == "clip"
    ]
    track_rows = [
        row for row in rows if isinstance(row, Mapping) and row.get("kind") == "track"
    ]
    result: dict[str, Any] = {}
    if action_id == "cutagent.action.fairlight.bus.assign" and len(track_rows) == 2:
        result.update(
            track=track_rows[0].get("trackIndex"),
            track_name=track_rows[0].get("trackName"),
            bus=track_rows[1].get("trackName"),
        )
    elif action_id == "cutagent.action.fairlight.bounce.mix_to_track" and (
        len(track_rows) == 2 and len(clip_rows) == 1
    ):
        result.update(
            bus=track_rows[0].get("trackName"),
            destination_track=track_rows[1].get("trackIndex"),
            clip_name=clip_rows[0].get("clipName"),
        )
    elif action_id == "cutagent.action.fairlight.bounce.track" and (
        len(track_rows) == 2 and len(clip_rows) == 1
    ):
        result.update(
            track=track_rows[0].get("trackIndex"),
            destination_track=track_rows[1].get("trackIndex"),
            clip_name=clip_rows[0].get("clipName"),
        )
    elif action_id == "cutagent.action.fairlight.bus.level" and len(track_rows) == 1:
        result["bus"] = track_rows[0].get("trackName")
    elif (
        action_id
        in {
            "cutagent.action.fairlight.mixer.fader",
            "cutagent.action.fairlight.mixer.pan",
        }
        and len(track_rows) == 1
    ):
        if isinstance(value, Mapping) and value.get("bus"):
            result["bus"] = track_rows[0].get("trackName")
        else:
            result["track"] = track_rows[0].get("trackIndex")
    if "clips" in parameters:
        clip_names = [row.get("clipName") for row in clip_rows]
        if len(clip_names) < 2 or any(
            not isinstance(name, str) or not name for name in clip_names
        ):
            raise FairlightEvaluationError(
                "STALE_REVISION",
                "Fairlight multi-clip lowering requires every signed live clip name.",
            )
        result["clips"] = clip_names
    if len(clip_rows) == 1:
        row = clip_rows[0]
        uses_exact_item_identity = (
            action_id == "cutagent.action.fairlight.item_source.patch"
            and "item_id" in parameters
        )
        if "clip_arg" in parameters:
            result["clip_arg"] = row.get("clipName")
        elif "clip" in parameters:
            result["clip"] = (
                row.get("nativeId")
                if action_id == "cutagent.action.fairlight.channel_map.set"
                or action_id.startswith("cutagent.action.fairlight.effect.")
                else row.get("clipName")
            )
        if "track" in parameters and not action_id.startswith(
            "cutagent.action.fairlight.effect."
        ):
            result["track"] = row.get("trackIndex")
        if "track_index" in parameters and not uses_exact_item_identity:
            result["track_index"] = row.get("trackIndex")
        if (
            "at" in parameters
            and action_id == "cutagent.action.fairlight.transition.add"
        ):
            result["at"] = f"{row.get('recordStartFrame')}f"
        if "clip_name" in parameters:
            result["clip_name"] = row.get("clipName")
        if "item_id" in parameters:
            result["item_id"] = row.get("nativeId")
        if "name" in parameters:
            result["name"] = row.get("clipName")
        if "start_frame" in parameters:
            result["start_frame"] = row.get("recordStartFrame")
        if "end_frame" in parameters:
            result["end_frame"] = row.get("recordEndFrameExclusive")
        if "record_frame" in parameters and not uses_exact_item_identity:
            result["record_frame"] = row.get("recordStartFrame")
    elif clip_rows and ({"clip", "clip_arg", "at"} & parameters):
        raise FairlightEvaluationError(
            "AMBIGUOUS_TIMELINE_ITEM",
            "Fairlight handler cannot lower multiple signed clips to one selector.",
        )
    if len(track_rows) == 1:
        row = track_rows[0]
        if "track" in parameters:
            result["track"] = row.get("trackIndex")
        if "track_index" in parameters:
            result["track_index"] = row.get("trackIndex")
        if "track_name" in parameters:
            result["track_name"] = row.get("trackName")
        if "index" in parameters:
            result["index"] = row.get("trackIndex")
    for key, item in result.items():
        if item is None or item == "Nonef":
            raise FairlightEvaluationError(
                "STALE_REVISION", f"Fairlight live locator omitted {key}."
            )
    supplied = response.get("handlerOverrides")
    if not isinstance(supplied, Mapping):
        raise FairlightEvaluationError(
            "STALE_REVISION", "Fairlight live overrides are unavailable."
        )
    for key, item in supplied.items():
        if key in result and result[key] != item:
            raise FairlightEvaluationError(
                "STALE_REVISION", "Fairlight live selector authorities disagree."
            )
        result[key] = item
    return result


def _exact_item_identity(item: Any) -> str:
    getter = getattr(item, "GetUniqueId", None)
    if not callable(getter):
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Fairlight clip link requires native timeline-item identity readback.",
        )
    try:
        value = getter()
    except Exception as exc:
        raise FairlightEvaluationError(
            "API_CALL_FAILED", "Fairlight timeline-item identity readback failed."
        ) from exc
    if not isinstance(value, str) or not value:
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Fairlight timeline-item identity is incomplete."
        )
    return value


def _execute_exact_clip_link(commands: Any, locators: Any) -> Mapping[str, Any]:
    """Link the exact carrier-signed native items, never a name-selected substitute."""
    if (
        not isinstance(locators, (list, tuple))
        or len(locators) < 2
        or any(
            not isinstance(row, Mapping) or row.get("kind") != "clip"
            for row in locators
        )
    ):
        raise FairlightEvaluationError(
            "EDIT_CONSTRAINT_VIOLATION",
            "Fairlight clip link requires at least two exact signed clip locators.",
        )
    commands.enforce_mutation_policy(
        "clip.link_unlink", intended_engine="api_native", mutating=True
    )
    connection = commands.get_connection(require_timeline=True)
    resolved: list[Any] = []
    resolved_ids: list[str] = []
    for locator in locators:
        track_index = locator.get("trackIndex")
        native_id = locator.get("nativeId")
        clip_name = locator.get("clipName")
        start_frame = locator.get("recordStartFrame")
        if (
            not isinstance(track_index, int)
            or isinstance(track_index, bool)
            or track_index < 1
            or not isinstance(native_id, str)
            or not native_id
            or not isinstance(clip_name, str)
            or not clip_name
            or not isinstance(start_frame, int)
            or isinstance(start_frame, bool)
        ):
            raise FairlightEvaluationError(
                "STALE_REVISION", "Fairlight clip link locator is incomplete."
            )
        try:
            candidates = connection.timeline.GetItemListInTrack("audio", track_index)
        except Exception as exc:
            raise FairlightEvaluationError(
                "API_CALL_FAILED", "Fairlight audio-track enumeration failed."
            ) from exc
        matches = []
        for item in candidates or []:
            if _exact_item_identity(item) != native_id:
                continue
            try:
                actual_name = item.GetName()
                actual_start = item.GetStart()
            except Exception as exc:
                raise FairlightEvaluationError(
                    "API_CALL_FAILED", "Fairlight signed clip readback failed."
                ) from exc
            if actual_name == clip_name and actual_start == start_frame:
                matches.append(item)
        if len(matches) != 1:
            raise FairlightEvaluationError(
                "STALE_REVISION",
                "Fairlight signed clip no longer resolves to exactly one native item.",
            )
        resolved.append(matches[0])
        resolved_ids.append(native_id)
    if len(set(resolved_ids)) != len(resolved_ids):
        raise FairlightEvaluationError(
            "EDIT_CONSTRAINT_VIOLATION",
            "Fairlight clip link contains duplicate native items.",
        )
    setter = getattr(connection.timeline, "SetClipsLinked", None)
    if not callable(setter):
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Timeline.SetClipsLinked is unavailable for exact Fairlight clip linking.",
        )
    try:
        applied = setter(resolved, True)
    except Exception as exc:
        raise FairlightEvaluationError(
            "API_CALL_FAILED", "Exact Fairlight clip linking failed."
        ) from exc
    if applied is False:
        raise FairlightEvaluationError(
            "API_CALL_FAILED", "Exact Fairlight clip linking was rejected."
        )
    expected = set(resolved_ids)
    checks = []
    for item, native_id in zip(resolved, resolved_ids, strict=True):
        getter = getattr(item, "GetLinkedItems", None)
        if not callable(getter):
            raise FairlightEvaluationError(
                "CAPABILITY_NEGOTIATION_FAILED",
                "Fairlight clip link requires native linked-item readback.",
            )
        try:
            linked_ids = {_exact_item_identity(peer) for peer in (getter() or [])}
        except FairlightEvaluationError:
            raise
        except Exception as exc:
            raise FairlightEvaluationError(
                "API_CALL_FAILED", "Fairlight linked-item readback failed."
            ) from exc
        missing = expected.difference({native_id}).difference(linked_ids)
        if missing:
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED",
                "Fairlight link readback omitted a signed native peer.",
            )
        checks.append({"ok": True, "nativeId": native_id})
    return {
        "action": "fairlight.clip.link",
        "changed": True,
        "operation": "link",
        "linked": True,
        "clip_count": len(resolved),
        "clips": [row["clipName"] for row in locators],
        "result": True,
        "verification": {"status": "verified", "checks": checks},
    }


def _execute_handler(
    context: Mapping[str, Any],
    descriptor: "FairlightEvaluationDescriptor",
    prepared: Mapping[str, Any],
) -> Mapping[str, Any]:
    from .commands import fairlight as commands

    lowering = prepared.get("lowering")
    resolved = lowering.get("resolved") if isinstance(lowering, Mapping) else None
    admission = (
        lowering.get("carrierAdmission") if isinstance(lowering, Mapping) else None
    )
    handler_name = _HANDLERS.get(descriptor.action_id)
    if (
        not isinstance(resolved, Mapping)
        or resolved.get("handlerName") != handler_name
        or not isinstance(resolved.get("kwargs"), Mapping)
        or not isinstance(admission, Mapping)
        or admission.get("actionId") != descriptor.action_id
        or admission.get("executionId") != context.get("executionId")
    ):
        raise FairlightEvaluationError(
            "EDIT_CONSTRAINT_VIOLATION", "Fairlight admitted lowering changed."
        )
    handler = getattr(commands, handler_name or "", None)
    if not callable(handler):
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Reviewed Fairlight handler is unavailable.",
        )
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__
    captured: list[Any] = []
    success_messages: list[str] = []
    private_bindings = context.get("privateBindings")
    fairlight_binding = (
        private_bindings.get("fairlight")
        if isinstance(private_bindings, Mapping)
        else None
    )
    cancellation = (
        fairlight_binding.get("cancellation")
        if isinstance(fairlight_binding, Mapping)
        else None
    )
    cancellation_path = (
        cancellation.get("requestPath") if isinstance(cancellation, Mapping) else None
    )
    cancellation_ack = (
        cancellation.get("acknowledgedPath")
        if isinstance(cancellation, Mapping)
        else None
    )
    if (cancellation_path is None) != (cancellation_ack is None) or (
        cancellation_path is not None
        and (
            not isinstance(cancellation_path, str)
            or not isinstance(cancellation_ack, str)
        )
    ):
        raise FairlightEvaluationError(
            "EDIT_CONSTRAINT_VIOLATION", "Fairlight cancellation custody is malformed."
        )
    with _HANDLER_LOCK:
        old_output = commands.output
        old_success = commands.success
        old_policy = commands.enforce_mutation_policy
        old_cancellation_path = os.environ.get("CUTAGENT_CLI_SDK_CANCELLATION_FILE")

        def admitted_policy(
            capability_id, *, intended_engine="api_native", mutating=True
        ):
            expected_mutating = descriptor.operation_class == "mutation"
            if (
                capability_id != descriptor.capability_id
                or bool(mutating) is not expected_mutating
            ):
                raise FairlightEvaluationError(
                    "EDIT_CONSTRAINT_VIOLATION",
                    "Fairlight handler policy scope changed.",
                )
            return old_policy(
                capability_id, intended_engine=intended_engine, mutating=False
            )

        try:
            commands.output = lambda data, **_options: captured.append(deepcopy(data))
            commands.success = lambda message: success_messages.append(str(message))
            commands.enforce_mutation_policy = admitted_policy
            if cancellation_path is not None:
                os.environ["CUTAGENT_CLI_SDK_CANCELLATION_FILE"] = cancellation_path
            kwargs = deepcopy(dict(resolved["kwargs"]))
            if "ctx" in inspect.signature(handler).parameters:
                kwargs["ctx"] = click.Context(
                    click.Command(descriptor.action_id), info_name=descriptor.action_id
                )
            try:
                if descriptor.action_id == "cutagent.action.fairlight.clip.link":
                    captured.append(
                        _execute_exact_clip_link(
                            commands, fairlight_binding.get("targets")
                        )
                    )
                else:
                    handler(**kwargs)
            except BaseException as error:
                cancellation_details = getattr(error, "details", None)
                if (
                    cancellation_path is not None
                    and Path(cancellation_path).is_file()
                    and isinstance(cancellation_details, Mapping)
                    and cancellation_details.get("cancellation_acknowledged") is True
                ):
                    Path(cancellation_ack).write_text("cancelled\n", encoding="utf-8")
                raise
        finally:
            commands.output = old_output
            commands.success = old_success
            commands.enforce_mutation_policy = old_policy
            if old_cancellation_path is None:
                os.environ.pop("CUTAGENT_CLI_SDK_CANCELLATION_FILE", None)
            else:
                os.environ["CUTAGENT_CLI_SDK_CANCELLATION_FILE"] = old_cancellation_path
    if not captured and not success_messages:
        raise FairlightEvaluationError(
            "API_CALL_FAILED", "Fairlight handler returned no structured result."
        )
    handler_result = captured[-1] if captured else {"message": success_messages[-1]}
    result = {"handlerResult": _canonical(handler_result)}
    if descriptor.operation_class == "mutation":
        post_state = _callback(
            descriptor.authority,
            context,
            descriptor.action_id,
            "verify",
            {
                "prepared": prepared,
                "handlerResult": result,
                "protectedState": prepared.get("preState", {}).get("protectedState"),
            },
        )
        result["verifiedProjectionContext"] = _canonical(post_state)
    return result


def _impact(
    context: Mapping[str, Any],
    descriptor: "FairlightEvaluationDescriptor",
    targets: list[dict[str, Any]],
    *,
    audition_required: bool = False,
) -> dict[str, Any]:
    if descriptor.operation_class == "read":
        return {
            "contractVersion": 1,
            "status": "read",
            "complete": True,
            "targetDigests": [
                prepared_action_digest("targets", {"orderedStableTargets": [target]})
                for target in targets
            ],
            "resultMaximumBytes": PREPARED_ACTION_MAX_RESULT_BYTES,
        }
    mutation_base = context.get("mutationBase")
    if not isinstance(mutation_base, Mapping):
        raise FairlightEvaluationError(
            "EDIT_CONSTRAINT_VIOLATION", "Fairlight mutation base is unavailable."
        )
    modalities = _required_modalities(
        descriptor.action_id, audition_required=audition_required
    )
    broad = descriptor.action_id in _BROAD_ACTION_IDS
    if descriptor.action_id in _CREATE_ACTION_IDS:
        effect_kind = "create"
    elif descriptor.action_id in _DELETE_ACTION_IDS:
        effect_kind = "delete"
    else:
        effect_kind = "update"
    effect_targets = []
    for target in targets:
        projected = {key: target[key] for key in ("kind", "stableId", "revision")}
        track_index = target.get("trackIndex")
        if (
            isinstance(track_index, int)
            and not isinstance(track_index, bool)
            and track_index > 0
        ):
            projected.update({"trackType": "audio", "trackIndex": track_index})
        effect_targets.append(projected)
    return {
        **_canonical(dict(mutation_base)),
        "status": "mutation",
        "effects": [
            {
                "operation": descriptor.action_id.removeprefix("cutagent.action."),
                "kind": effect_kind,
                "trackTypes": ["audio"],
                "targets": effect_targets,
                "placementIntent": "explicit",
                "broad": broad,
                "ambiguous": False,
                "complete": True,
            }
        ],
        "closedComposition": True,
        "complete": True,
        "ambiguous": False,
        "broad": broad,
        "executableStableTargetPrecondition": True,
        "verificationPolicy": {
            "minimumEvidence": modalities,
            "requireProtectedStatePreserved": True,
            "protectedTargetEvidence": "every_declared_target",
        },
    }


@dataclass(frozen=True)
class FairlightEvaluationDescriptor:
    action_id: str
    authority: "FairlightEvaluationExecutionAuthority"

    version = 1

    @property
    def operation_class(self) -> str:
        return PREPARED_ACTION_ACTION_METADATA[self.action_id]["operationClass"]

    @property
    def capability_id(self) -> str | None:
        return PREPARED_ACTION_ACTION_METADATA[self.action_id]["capabilityId"]

    @property
    def command_id(self) -> str:
        return self.action_id.removeprefix("cutagent.action.")

    def validate_input(self, value: Any) -> Any:
        _validate(value, _schema(self.action_id, "input"), "input")
        return _canonical(value)

    def prepare(self, context: Mapping[str, Any], value: Any) -> Mapping[str, Any]:
        response = _callback(
            self.authority,
            context,
            self.action_id,
            "prepare",
            {"normalizedInput": value},
            target_kinds=_carrier_target_kinds(
                self.action_id,
                len(
                    context.get("exactRequestBinding", {})
                    .get("identities", {})
                    .get("targetIds", ())
                ),
                value,
            ),
        )
        targets = _targets(context, response)
        private_target_locators = response["targets"]
        snapshot = response.get("snapshot")
        if self.action_id == "cutagent.action.fairlight.delete":
            closure = response.get("impactClosure")
            if (
                not isinstance(closure, Mapping)
                or closure.get("kind") != "track_delete"
                or closure.get("complete") is not True
                or not targets
                or closure.get("trackId") != targets[0]["stableId"]
                or closure.get("clipIds")
                != [target["stableId"] for target in targets[1:]]
                or not isinstance(closure.get("digest"), str)
                or _DIGEST.fullmatch(closure["digest"]) is None
            ):
                raise FairlightEvaluationError(
                    "EDIT_CONSTRAINT_VIOLATION",
                    "Fairlight track deletion lacks exhaustive live clip closure.",
                )
        if self.action_id == "cutagent.action.fairlight.solo_restore":
            requested_indices = [row["trackIndex"] for row in value["trackStates"]]
            signed_indices = [
                target.get("trackIndex")
                for target in private_target_locators
                if target.get("kind") == "track"
            ]
            if signed_indices != requested_indices or len(signed_indices) != len(
                private_target_locators
            ):
                raise FairlightEvaluationError(
                    "EDIT_CONSTRAINT_VIOLATION",
                    "Fairlight solo restore must sign every requested audio track in request order.",
                )
        if self.action_id == "cutagent.action.fairlight.channel_map.set":
            clip_targets = [
                target
                for target in private_target_locators
                if target.get("kind") == "clip"
            ]
            if (
                len(clip_targets) != 1
                or len(private_target_locators) != 1
                or clip_targets[0].get("clipName") != value.get("clipName")
            ):
                raise FairlightEvaluationError(
                    "EDIT_CONSTRAINT_VIOLATION",
                    "Fairlight channel-map set must sign the exact requested audio clip.",
                )
        if self.action_id == "cutagent.action.fairlight.clip.link":
            signed_names = [
                target.get("clipName")
                for target in private_target_locators
                if target.get("kind") == "clip"
            ]
            if signed_names != value.get("clips") or len(signed_names) != len(
                private_target_locators
            ):
                raise FairlightEvaluationError(
                    "EDIT_CONSTRAINT_VIOLATION",
                    "Fairlight clip link must sign every requested audio clip in request order.",
                )
        protected = response.get("protectedState")
        if not all(isinstance(item, Mapping) for item in (snapshot, protected)):
            raise FairlightEvaluationError(
                "CAPABILITY_UNAVAILABLE", "Fairlight preparation is incomplete."
            )
        audition_required = False
        if self.operation_class == "mutation":
            ranges = snapshot.get("audioRanges")
            if not isinstance(ranges, list):
                raise FairlightEvaluationError(
                    "CAPABILITY_NEGOTIATION_FAILED",
                    "Fairlight mutation audio-range custody is unavailable.",
                )
            if (
                not ranges
                and any(
                    target.get("kind") == "clip" for target in private_target_locators
                )
                and self.action_id not in _POST_MUTATION_AUDITION_ACTION_IDS
            ):
                raise FairlightEvaluationError(
                    "CAPABILITY_NEGOTIATION_FAILED",
                    "Fairlight clip mutation cannot prove target-range audio before dispatch.",
                )
        impact = _impact(context, self, targets, audition_required=audition_required)
        resolved_lowering = _prepare_lowering(
            self.action_id, value, _derived_overrides(self.action_id, response, value)
        )
        return {
            "targets": targets,
            "preState": {
                "snapshot": _canonical(snapshot),
                "protectedState": _canonical(protected),
                "artifactBaselines": _capture_artifact_baselines(self.action_id, value),
            },
            "impact": _canonical(impact),
            "lowering": {
                "normalizedInput": _canonical(value),
                "resolved": resolved_lowering,
                "carrierAdmission": {
                    "actionId": self.action_id,
                    "executionId": context.get("executionId"),
                },
            },
            "verification": {
                "minimumEvidence": _required_modalities(
                    self.action_id, audition_required=audition_required
                )
            },
            "recovery": {"strategy": "live_audit_then_manual_recovery"},
        }

    def resolve_current(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        response = _callback(
            self.authority,
            context,
            self.action_id,
            "current",
            {"preparedTargets": prepared.get("targets", [])},
        )
        fresh_artifacts = _validate_fresh_artifacts(prepared)
        if isinstance(response, dict):
            response["freshArtifacts"] = fresh_artifacts
        snapshot = response.get("snapshot")
        protected = response.get("protectedState")
        if not isinstance(snapshot, Mapping) or not isinstance(protected, Mapping):
            raise FairlightEvaluationError(
                "STALE_REVISION", "Fairlight current state is unavailable."
            )
        return {
            "targets": _targets(context, response),
            "preState": {
                "snapshot": _canonical(snapshot),
                "protectedState": _canonical(protected),
                "artifactBaselines": _canonical(
                    prepared.get("preState", {}).get("artifactBaselines", {})
                ),
            },
        }

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        authority = context.get("executionAuthority")
        invoke = getattr(authority, "invoke_admitted_handler", None)
        if not callable(invoke) or authority is not self.authority:
            raise FairlightEvaluationError(
                "EDIT_CONSTRAINT_VIOLATION",
                "Fairlight execution authority is unavailable.",
            )
        return invoke(context, self, prepared)

    def verify(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], _result: Any
    ) -> Mapping[str, Any]:
        if self.action_id in _FAIRLIGHT_READ_ACTION_IDS:
            if not isinstance(_result, dict):
                raise FairlightEvaluationError(
                    "VERIFICATION_FAILED",
                    "Fairlight read result cannot retain verification custody.",
                )
            independently_read = _execute_handler(context, self, prepared)
            first_projection = _project_read_result(self.action_id, prepared, _result)
            verified_projection = _project_read_result(
                self.action_id, prepared, independently_read
            )
            if first_projection != verified_projection:
                raise FairlightEvaluationError(
                    "VERIFICATION_FAILED",
                    "Fairlight read changed or disagreed with its independent verification read.",
                )
            _result["verifiedSemanticResult"] = verified_projection
        response = (
            _result.get("verifiedProjectionContext")
            if isinstance(_result, Mapping)
            else None
        )
        if not isinstance(response, Mapping):
            response = _callback(
                self.authority,
                context,
                self.action_id,
                "verify",
                {"prepared": prepared, "handlerResult": _result},
            )
        evidence = deepcopy(response.get("evidence"))
        if isinstance(evidence, list) and self.operation_class == "mutation":
            snapshot_digest = response.get("snapshot", {}).get("digest")
            if isinstance(snapshot_digest, str) and _DIGEST.fullmatch(snapshot_digest):
                evidence.append(
                    {
                        "modality": "structural",
                        "digest": snapshot_digest,
                        "summary": "Fresh action-scoped Fairlight post-state was read back.",
                    }
                )
            audition = (
                _result.get("auditionEvidence")
                if isinstance(_result, Mapping)
                else None
            )
            if isinstance(audition, Mapping):
                evidence.append(deepcopy(dict(audition)))
        required_modalities = prepared.get("verification", {}).get("minimumEvidence")
        if (
            response.get("outcome") != "passed"
            or response.get("protectedStatePreserved") is not True
            or not isinstance(evidence, list)
            or not evidence
            or not isinstance(required_modalities, list)
            or not set(required_modalities).issubset(
                {item.get("modality") for item in evidence if isinstance(item, Mapping)}
            )
            or any(
                not isinstance(item, Mapping)
                or item.get("modality")
                not in {
                    "readback",
                    "structural",
                    "file",
                    "rendered",
                    "visual",
                    "auditioned",
                }
                or not isinstance(item.get("digest"), str)
                or _DIGEST.fullmatch(item["digest"]) is None
                or not isinstance(item.get("summary"), str)
                or not item["summary"]
                or (
                    item.get("modality") == "auditioned"
                    and (
                        not isinstance(item.get("targetRangeDigest"), str)
                        or _DIGEST.fullmatch(item["targetRangeDigest"]) is None
                    )
                )
                for item in evidence
            )
        ):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED",
                "Fairlight live proof is incomplete; manual review is required.",
            )
        verification = {
            "outcome": "passed",
            "evidence": _canonical(evidence),
            "protectedStatePreserved": True,
        }
        if isinstance(_result, dict):
            _result["verifiedProjectionContext"] = _canonical(response)
            _result["carrierVerification"] = _canonical(verification)
        return verification

    def recover(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        _failure: BaseException,
    ) -> Mapping[str, Any]:
        try:
            response = _callback(
                self.authority,
                context,
                self.action_id,
                "recover",
                {"prepared": prepared},
            )
        except FairlightEvaluationError:
            return {
                "outcome": "manual_required",
                "attempted": True,
                "manualActionRequired": True,
            }
        recovery = response.get("recovery")
        if (
            not isinstance(recovery, Mapping)
            or recovery.get("manualActionRequired") is not True
        ):
            return {
                "outcome": "manual_required",
                "attempted": True,
                "manualActionRequired": True,
            }
        return _canonical(recovery)

    def project_result(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any
    ) -> Any:
        if self.action_id in _FAIRLIGHT_READ_ACTION_IDS:
            verified = (
                result.get("verifiedSemanticResult")
                if isinstance(result, Mapping)
                else None
            )
            if not isinstance(verified, Mapping):
                raise FairlightEvaluationError(
                    "VERIFICATION_FAILED",
                    "Fairlight read lacks independently correlated semantic verification.",
                )
            _validate(verified, _schema(self.action_id, "result"), "result")
            return _canonical(verified)
        if not isinstance(result, Mapping):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fairlight mutation lost result custody."
            )
        response = result.get("verifiedProjectionContext")
        verification = result.get("carrierVerification")
        if not isinstance(response, Mapping) or not isinstance(verification, Mapping):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED",
                "Fairlight mutation lacks correlated post-state custody.",
            )
        semantic = response.get("semanticResult")
        if semantic is None:
            semantic = self._project_owned_result(
                context, prepared, result, response, verification
            )
        _validate(semantic, _schema(self.action_id, "result"), "result")
        return _canonical(semantic)

    def _project_owned_result(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        result: Mapping[str, Any],
        response: Mapping[str, Any],
        verification: Mapping[str, Any],
    ) -> Any:
        from .fairlight_clip_runtime_projection import (
            FAIRLIGHT_CLIP_MUTATION_ACTION_IDS,
            project_fairlight_clip_runtime_result,
        )
        from .fairlight_library_runtime_projection import (
            ASSIGNED_FAIRLIGHT_COMMAND_IDS,
            project_fairlight_library_result,
        )
        from .fairlight_track_runtime_projection import (
            SUPPORTED_ACTION_IDS,
            project_fairlight_track_mutation_result,
        )

        raw = result.get("handlerResult")
        requested = prepared.get("lowering", {}).get("normalizedInput")
        binding = context.get("exactRequestBinding", {})
        identities = (
            binding.get("identities", {}) if isinstance(binding, Mapping) else {}
        )
        timeline_id = identities.get("timelineId")
        if self.action_id in {
            "cutagent.action.fairlight.effect.add",
            "cutagent.action.fairlight.effect.remove",
        } and not any(
            isinstance(row, Mapping) and row.get("kind") == "clip"
            for row in context.get("privateBindings", {})
            .get("fairlight", {})
            .get("targets", ())
        ):
            from .fairlight_clip_runtime_projection import (
                _runtime_carrier_evidence,
                _runtime_handler,
            )

            handler = _runtime_handler(result, self.command_id)
            readback = response.get("currentReadback")
            requested_effect = str(requested.get("effect") or "")
            normalized_effect = (
                requested_effect.casefold().replace("_", " ").replace("-", " ")
            )
            changed = handler.get("changed") is not False
            if normalized_effect in {"eq", "equalizer", "equaliser"}:
                if self.action_id.endswith(".remove") or not isinstance(
                    readback, Mapping
                ):
                    raise FairlightEvaluationError(
                        "VERIFICATION_FAILED",
                        "Fairlight timeline EQ readback is incomplete.",
                    )
                effect = {
                    "effectId": "fairlight.builtin.eq",
                    "displayName": "EQ",
                    "slotIndex": 1,
                    "enabled": True,
                }
                parameters = []
            else:
                if not isinstance(readback, Mapping) or readback.get("status") != "ok":
                    raise FairlightEvaluationError(
                        "VERIFICATION_FAILED",
                        "Fairlight timeline Dialogue Processor readback is incomplete.",
                    )
                enabled = self.action_id.endswith(".add")
                enable_fields = ("comp_enable", "gate_enable", "limiter_enable")
                if any(readback.get(name) is not enabled for name in enable_fields):
                    raise FairlightEvaluationError(
                        "VERIFICATION_FAILED",
                        "Fairlight timeline Dialogue Processor state differs from request.",
                    )
                effect = {
                    "effectId": "fairlight.builtin.dialogue_processor",
                    "displayName": "Dialogue Processor",
                    "slotIndex": 1,
                    "enabled": enabled,
                }
                parameters = [
                    {"name": name, "value": item, "writable": True}
                    for name, item in sorted(readback.items())
                    if name != "status" and isinstance(item, (bool, int, float, str))
                ]
            state = {"effect": effect, "parameters": parameters}
            audition_required = "auditioned" in set(
                prepared.get("verification", {}).get("minimumEvidence", ())
            )
            return {
                "actionId": self.action_id,
                "outcome": "succeeded" if changed else "no_change",
                "target": {"kind": "timeline", "timelineId": timeline_id},
                "before": None if changed else state,
                "after": state if changed else None,
                "affectedCount": 1 if changed else 0,
                "evidence": _runtime_carrier_evidence(
                    verification,
                    changed=changed,
                    audition_required=audition_required,
                ),
                "recovery": {
                    "required": False,
                    "manualRecoveryRequired": False,
                    "state": "none",
                    "guidance": None,
                },
            }
        if self.action_id in SUPPORTED_ACTION_IDS:
            pre_ranges = (
                prepared.get("preState", {}).get("snapshot", {}).get("audioRanges")
            )
            post_ranges = response.get("snapshot", {}).get("audioRanges")
            return project_fairlight_track_mutation_result(
                self.action_id,
                raw,
                timeline_id=timeline_id,
                requested=requested,
                current_readback=response.get("currentReadback"),
                before_readback=response.get("beforeReadback"),
                verification=verification,
                required_modalities=set(
                    prepared.get("verification", {}).get("minimumEvidence", ())
                ),
                target_audio_absent=(
                    isinstance(pre_ranges, list)
                    and not pre_ranges
                    and isinstance(post_ranges, list)
                    and not post_ranges
                ),
            )
        if self.command_id in ASSIGNED_FAIRLIGHT_COMMAND_IDS:
            return project_fairlight_library_result(
                {"timeline": {"timelineId": timeline_id}},
                self,
                prepared,
                result,
                fresh_artifacts=response.get("freshArtifacts"),
            )
        if self.action_id in FAIRLIGHT_CLIP_MUTATION_ACTION_IDS:
            projected = project_fairlight_clip_runtime_result(
                context, self, prepared, result, response, verification
            )
            if projected is not None:
                return projected
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED",
            "Fairlight action-specific post-state projection is unavailable.",
        )

    def validate_public_result(self, value: Any) -> bool:
        try:
            _validate(value, _schema(self.action_id, "result"), "result")
        except (FairlightEvaluationError, TypeError, ValueError):
            return False
        return True


@dataclass
class FairlightEvaluationExecutionAuthority:
    action_id: str
    _live_resolver: Any = None

    def bind_private_live_target_resolver(self, resolver: Any) -> None:
        if not callable(resolver):
            raise FairlightEvaluationError(
                "RUNTIME_INCOMPATIBLE", "Fairlight live resolver binding is invalid."
            )
        self._live_resolver = resolver

    def live_target_resolver(self):
        if not callable(self._live_resolver):
            raise FairlightEvaluationError(
                "CAPABILITY_NEGOTIATION_FAILED",
                "Fairlight live carrier authority is unavailable.",
            )
        return self._live_resolver

    def invoke_admitted_handler(
        self,
        context: Mapping[str, Any],
        descriptor: FairlightEvaluationDescriptor,
        prepared: Mapping[str, Any],
    ) -> Any:
        if (
            context.get("actionId") != self.action_id
            or descriptor.action_id != self.action_id
        ):
            raise FairlightEvaluationError(
                "EDIT_CONSTRAINT_VIOLATION",
                "Fairlight admitted action binding changed.",
            )
        return _execute_handler(context, descriptor, prepared)


def build_evaluation_bundle(
    action_ids: tuple[str, ...],
) -> tuple[
    Mapping[str, FairlightEvaluationDescriptor],
    Mapping[str, FairlightEvaluationExecutionAuthority],
]:
    authorities = {
        action_id: FairlightEvaluationExecutionAuthority(action_id)
        for action_id in action_ids
    }
    descriptors = {
        action_id: FairlightEvaluationDescriptor(action_id, authorities[action_id])
        for action_id in action_ids
    }
    return MappingProxyType(descriptors), MappingProxyType(authorities)
