"""Signed-registry Color prepared actions backed by the real CutAgent CLI.

The public SDK never sees the handler identity, native selector, local artifact
path, checkpoint, or DaVinci Resolve inspection payload held by this module.
"""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import math
import os
import re
import stat
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from ..connection import get_connection
from ..core import color_ops, gallery_ops, sdk_live_inspection, timeline_ops, version_ops
from .color_runtime_contracts import (
    InventoryValidationError,
    color_action_result_schema,
    color_result_kind,
    is_color_public_named_value,
    normalized_color_action_result_schema,
    reviewed_page_result_schema,
    validate_color_public_result,
)
from .color import (
    COLOR_ACTION_DESCRIPTORS,
    ColorActionDescriptor,
    PreparedColorAction,
    _bound_digest,
    _canonical_digest,
    _input_schema,
    _prepare_bound_descriptor,
    _reject_private_keys,
    _validate_typed_value,
)


CALLABLE_COLOR_ACTION_IDS = tuple(
    sorted(
        action_id
        for action_id, descriptor in COLOR_ACTION_DESCRIPTORS.items()
        if descriptor.advertised
    )
)
UNAVAILABLE_COLOR_ACTION_IDS = tuple(
    sorted(set(COLOR_ACTION_DESCRIPTORS) - set(CALLABLE_COLOR_ACTION_IDS))
)
COLOR_PREPARED_ACTION_CONTRIBUTION_NAME = "color"

_ARTIFACT_FIELDS = (
    "sourceArtifactId",
    "destinationArtifactId",
    "referenceArtifactId",
    "targetArtifactId",
    "beforeArtifactId",
    "afterArtifactId",
    "contactSheetArtifactId",
)
_COLOR_GUARD_ENV = "CUTAGENT_SDK_COLOR_GUARD"
_COLOR_NODE_STACK_LAYER_INDEX_ENV = "CUTAGENT_SDK_COLOR_NODE_STACK_LAYER_INDEX"
_PROJECT_GUARD_ENV = "CUTAGENT_SDK_PROJECT_GUARD"
_COLOR_GUARD_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
_COLOR_EXECUTION_LOCK = threading.RLock()
_OMITTED = object()
_PROJECT_PERSISTED_COLOR_ACTION_IDS = frozenset(
    {
        "cutagent.action.color.gallery.album.create",
        "cutagent.action.color.gallery.album.rename",
        "cutagent.action.color.gallery.album.switch",
    }
)
_POST_CHECKPOINT_COLOR_GUARD_REFRESH_ACTION_IDS = frozenset(
    {
        # The DB session performs its own last-safe-point guard immediately
        # before closing the project. Creating the recovery checkpoint saves
        # the project first, which can rewrite the opaque grade-body digest
        # without changing the selected clip or its semantic Color state.
        "cutagent.action.color.page.power_window_circle",
    }
)


def _persist_project_scoped_color_mutation(
    conn: Any, descriptor: ColorActionDescriptor
) -> None:
    """Flush Gallery catalog state before downstream Project.db custody reads."""
    if descriptor.action_id not in _PROJECT_PERSISTED_COLOR_ACTION_IDS:
        return
    save_project = getattr(getattr(conn, "project_manager", None), "SaveProject", None)
    if not callable(save_project) or save_project() is not True:
        raise InventoryValidationError(
            "Prepared Color Gallery mutation could not persist the active project"
        )


def _refresh_color_guard_after_checkpoint(
    conn: Any,
    context: Mapping[str, Any],
    descriptor: ColorActionDescriptor,
    clip_binding: Mapping[str, Any],
    node_index: int,
    node_stack_layer_index: int,
) -> None:
    """Rebind a DB route after its controlled recovery-checkpoint save."""

    if descriptor.action_id not in _POST_CHECKPOINT_COLOR_GUARD_REFRESH_ACTION_IDS:
        return
    observed = timeline_ops.inspect_sdk_live_state(
        conn,
        "color.current",
        deadline_at_ms=_deadline(context),
        node_stack_layer_index=node_stack_layer_index,
    )
    if (
        observed.get("before") != observed.get("after")
        or observed.get("summary_before") != observed.get("summary_after")
        or observed.get("color_before") != observed.get("color_after")
    ):
        raise InventoryValidationError(
            "Color target changed while creating its recovery checkpoint"
        )
    color = observed.get("color_after")
    target = color.get("target") if isinstance(color, Mapping) else None
    graph = color.get("node_graph") if isinstance(color, Mapping) else None
    nodes = graph.get("nodes") if isinstance(graph, Mapping) else None
    if (
        not isinstance(target, Mapping)
        or target.get("timeline_item_unique_id") != clip_binding.get("nativeId")
        or target.get("name") != clip_binding.get("selector")
        or not isinstance(nodes, list)
        or not any(
            isinstance(node, Mapping) and node.get("index") == node_index
            for node in nodes
        )
    ):
        raise InventoryValidationError(
            "Color target changed while creating its recovery checkpoint"
        )
    fresh_guard = observed.get("mutation_guard")
    if (
        not isinstance(fresh_guard, str)
        or _COLOR_GUARD_PATTERN.fullmatch(fresh_guard) is None
    ):
        raise InventoryValidationError(
            "Color recovery checkpoint did not produce a stable mutation guard"
        )
    os.environ[_COLOR_GUARD_ENV] = fresh_guard


def _gallery_album_inspection_selector(
    context: Mapping[str, Any],
    descriptor: ColorActionDescriptor,
    value: Mapping[str, Any],
    *,
    verification_phase: bool,
) -> str | None:
    if (
        verification_phase
        and descriptor.action_id == "cutagent.action.color.gallery.album.rename"
    ):
        new_name = value.get("newName")
        if not isinstance(new_name, str) or not new_name:
            raise InventoryValidationError(
                "Color Gallery album rename verification lacks its new selector"
            )
        return new_name
    selectors = context.get("privateSelectorBindings")
    album_binding = (
        selectors.get(value.get("albumId")) if isinstance(selectors, Mapping) else None
    )
    return album_binding.get("selector") if isinstance(album_binding, Mapping) else None


def _assert_color_request_revision_current(
    context: Mapping[str, Any],
    descriptor: ColorActionDescriptor,
    value: Mapping[str, Any],
    expected_revision: Any,
) -> None:
    """Validate explicit revisions or the carrier-signed revision for artifact actions."""
    accepted_revision = value.get(descriptor.revision_field)
    if accepted_revision is None:
        exact = context.get("exactRequestBinding")
        revisions = exact.get("revisions") if isinstance(exact, Mapping) else None
        revision_key = "timeline" if "timelineId" in descriptor.target_fields else "project"
        accepted_revision = revisions.get(revision_key) if isinstance(revisions, Mapping) else None
    if accepted_revision != expected_revision:
        raise InventoryValidationError("Color action revision is stale")


def _color_policy_effect_targets(
    targets: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Keep managed files in prepared custody but outside project-state policy targets."""
    return [dict(target) for target in targets if target.get("kind") != "artifact"]


def _mutable_copy(value: Any) -> Any:
    """Copy carrier-frozen mappings without depending on pickle support."""

    if isinstance(value, Mapping):
        return {key: _mutable_copy(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mutable_copy(child) for child in value]
    return deepcopy(value)


def _merge_carrier_mutation_base(
    context: Mapping[str, Any], domain_impact: Mapping[str, Any]
) -> dict[str, Any]:
    """Preserve the carrier-owned mutation binding and add only Color fields."""

    base = context.get("mutationBase")
    if not isinstance(base, Mapping):
        raise InventoryValidationError("Color mutation requires the carrier-owned mutation base")
    if set(base).intersection(domain_impact):
        raise InventoryValidationError("Color impact cannot replace carrier-owned mutation fields")
    return {**deepcopy(dict(base)), **deepcopy(dict(domain_impact))}


def bind_color_runtime_context(
    context: Mapping[str, Any],
    private_target_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Attach exact CLI-private target selectors to one Packet 0 invocation.

    The returned object is a defensive copy.  Native selectors never enter the
    public prepared-action request, impact, receipt, or projected result.
    """

    bound = deepcopy(dict(context))
    normalized = _normalize_color_target_bindings(private_target_bindings)
    if not normalized:
        raise InventoryValidationError("Color runtime requires at least one exact target binding")
    bound["privateTargetBindings"] = normalized
    return bound


def _normalize_color_target_bindings(
    private_target_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not isinstance(private_target_bindings, Mapping):
        raise InventoryValidationError("Color runtime target bindings are unavailable")
    normalized: dict[str, dict[str, Any]] = {}
    for stable_id, binding in private_target_bindings.items():
        if (
            not isinstance(stable_id, str)
            or not stable_id
            or not isinstance(binding, Mapping)
            or binding.get("kind") != "clip"
            or not isinstance(binding.get("selector"), str)
            or not binding["selector"]
            or not isinstance(binding.get("nativeId"), str)
            or not binding["nativeId"]
            or not isinstance(binding.get("trackIndex"), int)
            or isinstance(binding.get("trackIndex"), bool)
            or binding["trackIndex"] < 1
        ):
            raise InventoryValidationError("Color runtime target binding is incomplete")
        normalized[stable_id] = {
            "kind": "clip",
            "selector": str(binding["selector"]),
            "nativeId": str(binding["nativeId"]),
            "trackIndex": int(binding["trackIndex"]),
        }
    return normalized


def _normalize_color_selector_bindings(
    bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not isinstance(bindings, Mapping):
        raise InventoryValidationError("Color selector bindings are unavailable")
    normalized: dict[str, dict[str, Any]] = {}
    for selector, raw in bindings.items():
        if (
            not isinstance(selector, str)
            or not selector
            or not isinstance(raw, Mapping)
            or raw.get("kind") not in {"clip", "media", "fusion_composition"}
            or not isinstance(raw.get("stableId"), str)
            or not raw["stableId"]
            or not isinstance(raw.get("selector"), str)
            or not raw["selector"]
        ):
            raise InventoryValidationError("Color selector binding is incomplete")
        collection_kind = raw.get("collectionKind")
        if collection_kind is not None and (
            collection_kind not in {
                "groups", "albums", "stills", "powerGrades", "powerGradeAlbums",
                "qualifiers", "trackers", "windows", "versions",
            }
            or not isinstance(raw.get("ordinal"), int)
            or isinstance(raw.get("ordinal"), bool)
            or raw["ordinal"] < 1
            or not isinstance(raw.get("parent"), Mapping)
            or not isinstance(raw.get("capturedRevision"), str)
            or not raw["capturedRevision"]
            or not (
                selector == raw.get("stableId")
                or (collection_kind == "versions" and selector == raw.get("selector"))
            )
        ):
            raise InventoryValidationError("Color snapshot selector binding is incomplete")
        record = _mutable_copy(raw)
        if record["kind"] == "clip" and (
            not isinstance(record.get("nativeId"), str)
            or not record["nativeId"]
            or not isinstance(record.get("trackIndex"), int)
            or isinstance(record.get("trackIndex"), bool)
            or record["trackIndex"] < 1
        ):
            raise InventoryValidationError("Color clip selector lacks exact native identity")
        normalized[selector] = record
    return normalized


def _normalize_color_managed_artifacts(
    artifacts: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not isinstance(artifacts, Mapping):
        raise InventoryValidationError("Color managed artifact bindings are unavailable")
    normalized: dict[str, dict[str, Any]] = {}
    for artifact_id, raw in artifacts.items():
        path = raw.get("path") if isinstance(raw, Mapping) else None
        digest = raw.get("sha256") if isinstance(raw, Mapping) else None
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or not isinstance(path, str)
            or not Path(path).is_absolute()
            or (digest is not None and (
                not isinstance(digest, str)
                or re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", digest) is None
            ))
        ):
            raise InventoryValidationError("Color managed artifact binding is incomplete")
        normalized[artifact_id] = _mutable_copy(raw)
    return normalized


def build_production_color_runtime_context(
    signed_context: Mapping[str, Any],
    *,
    mutation_base: Mapping[str, Any] | None,
    private_target_bindings: Mapping[str, Mapping[str, Any]],
    private_selector_bindings: Mapping[str, Mapping[str, Any]],
    private_named_clip_bindings: Mapping[str, Mapping[str, Any]],
    private_all_timeline_item_ids: list[str] | tuple[str, ...],
    private_managed_artifacts: Mapping[str, Mapping[str, Any]],
    private_mutation_guard: str | None = None,
) -> dict[str, Any]:
    """Adapt carrier-captured truth into the complete private Color context.

    Every value is supplied by the carrier's live capture authority. Display
    names are never resolved or inferred here.
    """

    if not isinstance(signed_context, Mapping):
        raise InventoryValidationError("Color signed runtime context is unavailable")
    context = _mutable_copy(signed_context)
    project = context.get("project")
    timeline = context.get("timeline")
    execution = context.get("execution")
    if (
        not isinstance(project, Mapping)
        or not isinstance(project.get("projectId"), str)
        or not isinstance(project.get("projectRevision"), str)
        or not isinstance(timeline, Mapping)
        or not isinstance(execution, Mapping)
    ):
        raise InventoryValidationError("Color signed project, timeline, or execution binding is incomplete")

    if private_mutation_guard is not None:
        if _COLOR_GUARD_PATTERN.fullmatch(private_mutation_guard) is None:
            raise InventoryValidationError("Color captured mutation guard is invalid")
        signed_mutation_guard = timeline.get("mutationGuard")
        if signed_mutation_guard != private_mutation_guard:
            raise InventoryValidationError("Color captured mutation guard changed during capture")
        context["timeline"]["mutationGuard"] = private_mutation_guard

    targets = _normalize_color_target_bindings(private_target_bindings)
    selectors = _normalize_color_selector_bindings(private_selector_bindings)
    named = _normalize_color_selector_bindings(private_named_clip_bindings)
    if any(record.get("kind") != "clip" for record in named.values()):
        raise InventoryValidationError("Color named-clip bindings must identify exact clips")
    for record in (*selectors.values(), *named.values()):
        if record.get("kind") != "clip":
            continue
        target = targets.get(record["stableId"])
        if not isinstance(target, Mapping) or any(
            target.get(key) != record.get(key)
            for key in ("selector", "nativeId", "trackIndex")
        ):
            raise InventoryValidationError("Color clip selector drifted from its exact target binding")
    if (
        not isinstance(private_all_timeline_item_ids, (list, tuple))
        or any(not isinstance(item, str) or not item for item in private_all_timeline_item_ids)
        or len(set(private_all_timeline_item_ids)) != len(private_all_timeline_item_ids)
    ):
        raise InventoryValidationError("Color all-timeline inventory is malformed")
    timeline_item_ids = list(private_all_timeline_item_ids)
    if any(item not in targets for item in timeline_item_ids):
        raise InventoryValidationError("Color all-timeline inventory contains an unbound item")

    context["privateTargetBindings"] = targets
    context["privateSelectorBindings"] = selectors
    context["privateNamedClipBindings"] = named
    context["privateAllTimelineItemIds"] = timeline_item_ids
    context["privateManagedArtifacts"] = _normalize_color_managed_artifacts(
        private_managed_artifacts
    )

    embedded_mutation_base = context.get("mutationBase")
    normalized_mutation_base = (
        _mutable_copy(mutation_base) if mutation_base is not None else None
    )
    if (
        embedded_mutation_base is not None
        and normalized_mutation_base is not None
        and embedded_mutation_base != normalized_mutation_base
    ):
        raise InventoryValidationError("Color signed mutation base changed during capture")
    accepted_mutation_base = (
        normalized_mutation_base
        if normalized_mutation_base is not None
        else embedded_mutation_base
    )
    if accepted_mutation_base is not None:
        required = {
            "contractVersion", "carrier", "minimumBinding", "registryDigest",
            "canonicalRequestDigest", "referencedPayloadDigests", "requestId",
            "operationId", "executionId", "scopeId", "scopeRevision",
            "projectLibraryId", "projectId", "projectRevision",
        }
        if (
            not isinstance(accepted_mutation_base, Mapping)
            or not required.issubset(accepted_mutation_base)
        ):
            raise InventoryValidationError("Color carrier mutation base is incomplete")
        if (
            accepted_mutation_base.get("projectId") != project.get("projectId")
            or accepted_mutation_base.get("projectRevision") != project.get("projectRevision")
            or any(accepted_mutation_base.get(key) != execution.get(key) for key in (
                "requestId", "operationId", "executionId"
            ))
            or (
                accepted_mutation_base.get("timelineId") is not None
                and accepted_mutation_base.get("timelineId") != timeline.get("timelineId")
            )
            or (
                accepted_mutation_base.get("timelineRevision") is not None
                and accepted_mutation_base.get("timelineRevision") != timeline.get("timelineRevision")
            )
        ):
            raise InventoryValidationError("Color carrier mutation binding drifted")
        context["mutationBase"] = _mutable_copy(accepted_mutation_base)
        context["mutationPolicy"] = {
            key: _mutable_copy(accepted_mutation_base[key])
            for key in ("registryDigest", "scopeId", "scopeRevision", "projectLibraryId")
        }
    return context


def _deadline(context: Mapping[str, Any]) -> int:
    candidate = context.get("deadlineAtMs")
    if isinstance(candidate, int) and candidate > int(time.time() * 1000):
        return candidate
    return int(time.time() * 1000) + 60_000


def _public_result_value(value: Any) -> Any:
    """Project handler data to JSON-safe values while dropping private leaves."""

    if value is None or isinstance(value, (bool, int, float)):
        return deepcopy(value)
    if isinstance(value, str):
        try:
            _reject_private_keys(value)
        except InventoryValidationError:
            return _OMITTED
        return value
    if isinstance(value, Mapping):
        projected: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                continue
            try:
                _reject_private_keys({key: None})
            except InventoryValidationError:
                continue
            public_child = _public_result_value(child)
            if public_child is not _OMITTED:
                projected[key] = public_child
        return projected
    if isinstance(value, (list, tuple)):
        return [
            public_child
            for item in value
            if (public_child := _public_result_value(item)) is not _OMITTED
        ]
    return _OMITTED


def _target_binding(context: Mapping[str, Any], stable_id: str, kind: str) -> Mapping[str, Any]:
    bindings = context.get("privateTargetBindings")
    binding = bindings.get(stable_id) if isinstance(bindings, Mapping) else None
    if not isinstance(binding, Mapping) or binding.get("kind") != kind:
        raise InventoryValidationError(f"Color {kind} target is not privately bound to this SDK session")
    selector = binding.get("selector")
    if not isinstance(selector, str) or not selector:
        raise InventoryValidationError(f"Color {kind} target has no exact native selector")
    return binding


def _artifact_path(context: Mapping[str, Any], artifact_id: str) -> str:
    artifacts = context.get("privateManagedArtifacts")
    record = artifacts.get(artifact_id) if isinstance(artifacts, Mapping) else None
    path = record.get("path") if isinstance(record, Mapping) else None
    if not isinstance(path, str) or not Path(path).is_absolute():
        raise InventoryValidationError("Color managed artifact is unavailable")
    return path


def _file_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _artifact_custody(
    descriptor: ColorActionDescriptor,
    value: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    managed = context.get("privateManagedArtifacts")
    records: dict[str, dict[str, Any]] = {}
    binding_by_field = dict(descriptor.private_bindings)
    for field_name in _ARTIFACT_FIELDS:
        artifact_id = value.get(field_name)
        if not isinstance(artifact_id, str):
            continue
        managed_record = managed.get(artifact_id) if isinstance(managed, Mapping) else None
        path_text = managed_record.get("path") if isinstance(managed_record, Mapping) else None
        if not isinstance(path_text, str) or not Path(path_text).is_absolute():
            raise InventoryValidationError("Color managed artifact is unavailable")
        path = Path(path_text)
        binding = binding_by_field.get(field_name, "")
        role = (
            "source"
            if binding in {"artifact:path", "artifact:input_file", "artifact:source"}
            else "destination"
        )
        if role == "source":
            if not path.is_file():
                raise InventoryValidationError("Color source artifact is unavailable")
            sha256, byte_length = _file_sha256(path)
            expected = managed_record.get("sha256") if isinstance(managed_record, Mapping) else None
            expected = expected.removeprefix("sha256:") if isinstance(expected, str) else None
            if expected != sha256:
                raise InventoryValidationError("Color source artifact digest changed")
            records[artifact_id] = {
                "artifactId": artifact_id,
                "path": str(path),
                "role": role,
                "sha256": sha256,
                "byteLength": byte_length,
                "identity": deepcopy(managed_record.get("identity")),
            }
        else:
            identity = managed_record.get("reservationIdentity") if isinstance(managed_record, Mapping) else None
            if not isinstance(identity, Mapping) or not path.is_file() or path.is_symlink():
                raise InventoryValidationError("Color destination artifact has no managed reservation")
            observed = path.stat()
            if (
                observed.st_size != 0
                or observed.st_dev != identity.get("device")
                or observed.st_ino != identity.get("inode")
                or stat.S_IMODE(observed.st_mode) & 0o077
            ):
                raise InventoryValidationError("Color destination artifact reservation identity changed")
            records[artifact_id] = {
                "artifactId": artifact_id,
                "path": str(path),
                "role": role,
                "existed": False,
                "reservationIdentity": deepcopy(dict(identity)),
            }
    return records


def _revalidate_artifact_custody(records: Mapping[str, Any]) -> None:
    for record in records.values():
        if not isinstance(record, Mapping):
            raise InventoryValidationError("Color artifact custody is invalid")
        path = Path(str(record.get("path") or ""))
        if record.get("role") == "source":
            identity = record.get("identity")
            observed = path.stat() if path.is_file() and not path.is_symlink() else None
            if not path.is_file() or _file_sha256(path) != (
                record.get("sha256"),
                record.get("byteLength"),
            ) or not isinstance(identity, Mapping) or observed is None or (
                observed.st_dev != identity.get("device")
                or observed.st_ino != identity.get("inode")
                or abs(observed.st_mtime * 1000 - float(identity.get("mtimeMs", -1))) > 1
                or abs(observed.st_ctime * 1000 - float(identity.get("ctimeMs", -1))) > 1
            ):
                raise InventoryValidationError("Color source artifact changed before execution")
        else:
            identity = record.get("reservationIdentity")
            observed = path.stat() if path.is_file() and not path.is_symlink() else None
            if not isinstance(identity, Mapping) or observed is None or (
                observed.st_size != 0
                or observed.st_dev != identity.get("device")
                or observed.st_ino != identity.get("inode")
                or stat.S_IMODE(observed.st_mode) & 0o077
            ):
                raise InventoryValidationError("Color destination artifact reservation changed before execution")


def _destination_artifact_evidence(records: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for artifact_id, record in records.items():
        if not isinstance(record, Mapping) or record.get("role") != "destination":
            continue
        path = Path(str(record.get("path") or ""))
        if not path.is_file():
            raise InventoryValidationError("Color destination artifact was not created")
        sha256, byte_length = _file_sha256(path)
        if byte_length < 1:
            raise InventoryValidationError("Color destination artifact is empty")
        evidence.append(
            {"artifactId": artifact_id, "sha256": sha256, "byteLength": byte_length}
        )
    return evidence


def _camel_case(name: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", name) if word]
    if not words:
        return "value"
    return words[0].lower() + "".join(word[:1].upper() + word[1:] for word in words[1:])


def _safe_named_values(value: Any, *, maximum: int = 512) -> list[dict[str, Any]]:
    if not isinstance(value, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    for key, item in value.items():
        if len(rows) >= maximum or not isinstance(key, str):
            break
        normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
        if normalized_key.endswith(("id", "uuid", "path")) or normalized_key in {
            "id",
            "uniqueid",
            "selector",
            "route",
            "method",
            "engine",
            "command",
            "database",
        }:
            continue
        public = _public_result_value(item)
        if (
            public is _OMITTED
            or not isinstance(public, (type(None), bool, int, float, str))
            or not is_color_public_named_value(public)
        ):
            continue
        rows.append({"name": _camel_case(key), "value": public})
    return rows


def _public_target(
    context: Mapping[str, Any],
    value: Mapping[str, Any],
) -> dict[str, Any]:
    project = context.get("project", {})
    timeline = context.get("timeline", {})
    return {
        "projectId": value.get("projectId") or project.get("projectId"),
        "projectRevision": project.get("projectRevision"),
        "timelineId": value.get("timelineId") or timeline.get("timelineId") or None,
        "timelineRevision": timeline.get("timelineRevision") or None,
        "timelineItemId": value.get("timelineItemId") or None,
        "snapshotTimelineItemId": value.get("snapshotTimelineItemId") or None,
        "colorRevision": value.get("revision") or None,
        "trackIndex": value.get("trackIndex") or None,
        "recordFrame": value.get("recordFrame") if isinstance(value.get("recordFrame"), int) else None,
        "nodeIndex": value.get("nodeIndex") or None,
        "groupId": value.get("groupId") or None,
        "albumId": value.get("albumId") or None,
        "stillId": value.get("stillId") or None,
        "windowId": value.get("windowId") or None,
        "trackerId": value.get("trackerId") or None,
    }


def _artifact_kind(descriptor: ColorActionDescriptor, value: Mapping[str, Any]) -> str:
    if descriptor.command_id in {"color.export_lut", "color.huesat"}:
        return "lut"
    if descriptor.command_id in {"color.gallery.still.export"}:
        return "still"
    if descriptor.command_id == "color.thumbnail":
        return "thumbnail"
    if "frame" in descriptor.command_id or "snapshot" in descriptor.command_id:
        return "frame"
    if descriptor.command_id == "color.comp.export":
        return "graph"
    return "other"


def _artifact_media_type(kind: str, value: Mapping[str, Any]) -> str:
    if kind == "lut":
        return "application/x-cube-lut"
    if kind == "graph":
        return "application/json"
    if value.get("format") == "drx":
        return "application/x-davinci-resolve-grade"
    if value.get("format") == "jpg":
        return "image/jpeg"
    return "image/png"


_STRUCTURAL_EFFECT_STRATEGIES = {
    "cutagent.action.color.comp.flatten": "comp_flattened",
    "cutagent.action.color.comp.repair": "comp_repaired",
    "cutagent.action.color.gallery.album.create": "album_created",
    "cutagent.action.color.gallery.album.rename": "album_renamed",
    "cutagent.action.color.gallery.album.switch": "album_selected",
    "cutagent.action.color.gallery.still.delete": "still_deleted",
    "cutagent.action.color.gallery.still.grab": "still_grabbed",
    "cutagent.action.color.gallery.still.import": "still_imported",
    "cutagent.action.color.gallery.still.label": "still_labeled",
    "cutagent.action.color.group.add": "group_created",
    "cutagent.action.color.group.assign": "clip_group_assigned",
    "cutagent.action.color.group.delete": "group_deleted",
    "cutagent.action.color.group.remove": "clip_group_removed",
    "cutagent.action.color.group.rename": "group_renamed",
    "cutagent.action.color.node.cache": "node_cache_set",
    "cutagent.action.color.node.disable": "node_enabled_ack",
    "cutagent.action.color.node.enable": "node_enabled_ack",
    "cutagent.action.color.node.label_set": "node_label_set",
    "cutagent.action.color.node.lut_set": "node_lut_set",
    "cutagent.action.color.page.power_window_circle": "power_window_circle",
    "cutagent.action.color.page.power_window_track": "power_window_tracked",
    "cutagent.action.color.tracker.add": "tracker_added",
    "cutagent.action.color.window.ellipse": "window_ellipse_added",
    "cutagent.action.color.node.reset": "node_reset_ack",
    "cutagent.action.color.power_grade.album.create": "power_grade_album_created",
    "cutagent.action.color.version.activate": "version_loaded",
    "cutagent.action.color.version.add": "version_created",
    "cutagent.action.color.version.delete": "version_deleted",
    "cutagent.action.color.version.duplicate": "version_created",
    "cutagent.action.color.version.load": "version_loaded",
    "cutagent.action.color.version.rollback": "version_loaded",
    "cutagent.action.page.switch": "page_selected",
}
_EXPECTED_STRUCTURAL_MUTATIONS = {
    action_id for action_id, descriptor in COLOR_ACTION_DESCRIPTORS.items()
    if descriptor.advertised
    and descriptor.operation_class == "mutation"
    and descriptor.verification_profile == "structural_readback_and_revision"
}
if set(_STRUCTURAL_EFFECT_STRATEGIES) != _EXPECTED_STRUCTURAL_MUTATIONS:
    raise InventoryValidationError("Color structural verification strategy registry is incomplete")


def _selected_color_state(state: Mapping[str, Any]) -> Mapping[str, Any]:
    selected = state.get("selectedColor")
    if not isinstance(selected, Mapping) or len(selected) != 1:
        return {}
    item = next(iter(selected.values()))
    return item if isinstance(item, Mapping) else {}


def _selector_name(prepared: Mapping[str, Any], stable_id: Any) -> str | None:
    bindings = prepared.get("lowering", {}).get("privateSelectorBindings", {})
    record = bindings.get(stable_id) if isinstance(bindings, Mapping) else None
    selector = record.get("selector") if isinstance(record, Mapping) else None
    return selector if isinstance(selector, str) and selector else None


def _rows_have(rows: Any, field: str, expected: Any) -> bool:
    return isinstance(rows, list) and any(
        isinstance(row, Mapping) and row.get(field) == expected for row in rows
    )


def _power_grade_album_names(conn: Any) -> list[str]:
    gallery = color_ops._get_gallery(conn)
    getter = getattr(gallery, "GetGalleryPowerGradeAlbums", None)
    if not callable(getter):
        raise InventoryValidationError("PowerGrade album readback is unavailable")
    albums = gallery_ops._normalize_stills(getter() or [])
    return [
        str(gallery_ops._album_name(album, f"Power Grade {index}", gallery=gallery))
        for index, album in enumerate(albums, 1)
    ]


def _snapshot_selector_id(record: Mapping[str, Any]) -> str:
    prefix = {
        "groups": "group_", "albums": "album_", "stills": "still_",
        "powerGradeAlbums": "album_", "powerGrades": "color_entity_",
        "qualifiers": "color_entity_", "trackers": "color_entity_",
        "windows": "color_entity_", "versions": "color_entity_",
    }.get(record.get("collectionKind"))
    if prefix is None:
        raise InventoryValidationError("Color snapshot selector kind is unavailable")
    parent = record["parent"]
    canonical_parent = {
        "projectId": parent.get("projectId"),
        "timelineId": parent.get("timelineId"),
        "timelineItemId": parent.get("timelineItemId"),
        "compositionIndex": parent.get("compositionIndex"),
        **({"albumId": parent.get("albumId")} if "albumId" in parent else {}),
    }
    payload = {
        "kind": record["collectionKind"],
        "ordinal": record["ordinal"],
        "label": record["selector"],
        "parent": canonical_parent,
        "revision": record["capturedRevision"],
    }
    digest = base64.urlsafe_b64encode(hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).digest()).decode("ascii").rstrip("=")
    return f"{prefix}f{digest}"


def _inventory_rows_for_selector(
    conn: Any,
    collection_kind: str,
    *,
    clip_name: str | None,
    comp_index: int,
    album_name: str | None,
) -> list[Mapping[str, Any]]:
    if collection_kind == "groups":
        return color_ops.list_color_groups(conn)
    if collection_kind == "albums":
        return color_ops.list_gallery_albums(conn)
    if collection_kind == "stills":
        return gallery_ops.list_stills(conn, album=album_name)
    if collection_kind == "powerGrades":
        return color_ops.list_power_grades(conn)
    if collection_kind == "powerGradeAlbums":
        return [{"index": index, "name": name} for index, name in enumerate(_power_grade_album_names(conn), 1)]
    if collection_kind == "qualifiers":
        return color_ops.list_qualifiers(conn, clip_name, comp_index=comp_index)
    if collection_kind == "trackers":
        return color_ops.list_trackers(conn, clip_name, comp_index=comp_index)
    if collection_kind == "windows":
        return color_ops.list_windows(conn, clip_name, comp_index=comp_index)
    if collection_kind == "versions":
        return color_ops.list_color_versions(conn, clip_name)
    raise InventoryValidationError("Color snapshot selector inventory is unsupported")


def _row_label(row: Mapping[str, Any]) -> str | None:
    for key in ("label", "name", "version_name", "versionName", "album", "still"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _selector_inventory_revision(collection_kind: str, rows: list[Mapping[str, Any]]) -> str:
    items = []
    for fallback, row in enumerate(rows, 1):
        ordinal_value = row.get("index", row.get("order", row.get("position", fallback)))
        ordinal = ordinal_value if isinstance(ordinal_value, int) and not isinstance(ordinal_value, bool) and ordinal_value > 0 else fallback
        items.append({
            "ordinal": ordinal,
            "label": _row_label(row),
        })
    digest = hashlib.sha256(json.dumps(
        {"kind": collection_kind, "items": items},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return f"revision_color_selector_{digest}"


_VERIFICATION_MUTATED_SELECTOR_COLLECTIONS = {
    "cutagent.action.color.gallery.album.rename": "albums",
    "cutagent.action.color.gallery.still.delete": "stills",
    "cutagent.action.color.gallery.still.label": "stills",
}


def _revalidate_snapshot_selectors(
    conn: Any,
    context: Mapping[str, Any],
    descriptor: ColorActionDescriptor,
    value: Mapping[str, Any],
) -> None:
    records = context.get("privateSelectorBindings")
    if not isinstance(records, Mapping):
        return
    selected_ids = {
        item for field in (
            "groupId", "albumId", "stillId", "stillSelector", "qualifierName",
            "trackerName", "windowName", "name",
        ) for item in [value.get(field)] if isinstance(item, str)
    }
    for stable_id in tuple(selected_ids):
        selected = records.get(stable_id)
        parent = selected.get("parent") if isinstance(selected, Mapping) else None
        album_id = parent.get("albumId") if isinstance(parent, Mapping) else None
        if isinstance(album_id, str):
            selected_ids.add(album_id)
    snapshot_records = [
        (stable_id, record) for stable_id, record in records.items()
        if isinstance(record, Mapping) and record.get("collectionKind") is not None
        and (stable_id in selected_ids or descriptor.operation_class == "read")
    ]
    if not snapshot_records:
        return
    clip_binding = context.get("privateTargetBindings", {}).get(value.get("timelineItemId"))
    clip_name = clip_binding.get("selector") if isinstance(clip_binding, Mapping) else None
    comp_index = int(value.get("compIndex", 1))
    cache: dict[tuple[str, str | None], list[Mapping[str, Any]]] = {}
    for stable_id, record in snapshot_records:
        parent = record.get("parent")
        timeline_scoped = record.get("collectionKind") in {"qualifiers", "trackers", "windows", "versions"}
        expected_parent = {
            "projectId": context.get("project", {}).get("projectId"),
            "timelineId": value.get("timelineId") if timeline_scoped else None,
            "timelineItemId": value.get("timelineItemId") if timeline_scoped else None,
            "compositionIndex": value.get("compIndex") if timeline_scoped else None,
        }
        if not isinstance(parent, Mapping) or any(parent.get(key) != expected for key, expected in expected_parent.items()) or _snapshot_selector_id(record) != record.get("stableId"):
            raise InventoryValidationError("Color snapshot selector parent or revision is stale")
        album_id = parent.get("albumId")
        album_record = records.get(album_id) if isinstance(album_id, str) else None
        album_name = album_record.get("selector") if isinstance(album_record, Mapping) else None
        if descriptor.action_id == "cutagent.action.color.page.still_match" and record.get("collectionKind") == "stills":
            current_album = color_ops.get_current_album_info(conn)
            current_label = _row_label(current_album) if isinstance(current_album, Mapping) else None
            current_ordinal = current_album.get("index") if isinstance(current_album, Mapping) else None
            if not isinstance(album_record, Mapping) or current_label != album_name or (
                isinstance(current_ordinal, int) and current_ordinal != album_record.get("ordinal")
            ):
                raise InventoryValidationError("Current Color album changed before still-match execution")
        key = (str(record["collectionKind"]), album_name)
        rows = cache.setdefault(key, _inventory_rows_for_selector(
            conn, key[0], clip_name=clip_name, comp_index=comp_index, album_name=album_name
        ))
        labels = [_row_label(row) for row in rows]
        if descriptor.operation_class == "mutation" and record.get("collectionKind") != "stills" and len(labels) != len(set(labels)):
            raise InventoryValidationError("Color selector inventory contains duplicate labels")
        allow_expected_selector_change = (
            context.get("privateColorInspectionPhase") == "verification"
            and stable_id in selected_ids
            and _VERIFICATION_MUTATED_SELECTOR_COLLECTIONS.get(descriptor.action_id) == record.get("collectionKind")
        )
        if allow_expected_selector_change:
            continue
        if record.get("capturedRevision") != _selector_inventory_revision(key[0], rows):
            raise InventoryValidationError("Color snapshot selector inventory revision is stale")
        ordinal = int(record["ordinal"])
        matching_rows = [row for fallback, row in enumerate(rows, 1) if (
            isinstance(row, Mapping)
            and row.get("index", row.get("order", row.get("position", fallback))) == ordinal
        )]
        expected_label = record.get("inventoryLabel", record.get("selector")) if record.get("collectionKind") == "stills" else record.get("selector")
        if len(matching_rows) != 1 or (_row_label(matching_rows[0]) or "") != (expected_label or ""):
            raise InventoryValidationError("Color snapshot selector changed before execution")


def _requested_effect_matches(
    descriptor: ColorActionDescriptor,
    value: Mapping[str, Any],
    native_result: Any,
    before_state: Mapping[str, Any],
    after_state: Mapping[str, Any],
    prepared: Mapping[str, Any],
    artifact_evidence: Any,
) -> bool:
    if descriptor.action_id == "cutagent.action.color.fx.apply":
        native = native_result if isinstance(native_result, Mapping) else {}
        verification = native.get("verification")
        return (
            _rendered_frame_proof(native) is not None
            and isinstance(verification, Mapping)
            and verification.get("status") == "verified"
            and verification.get("node_index") == value.get("nodeIndex")
            and isinstance(verification.get("plugin_id"), str)
            and bool(verification["plugin_id"])
        )
    if descriptor.verification_profile == "color_readback_revision_and_rendered_frame":
        return _rendered_frame_proof(native_result) is not None
    if descriptor.verification_profile == "artifact_hash_nonempty_and_context":
        return isinstance(artifact_evidence, list) and bool(artifact_evidence)
    strategy = _STRUCTURAL_EFFECT_STRATEGIES.get(descriptor.action_id)
    if strategy is None:
        return False
    native = native_result if isinstance(native_result, Mapping) else {}
    semantic = after_state.get("semanticReadback", {})
    before_semantic = before_state.get("semanticReadback", {})
    selected = _selected_color_state(after_state)
    before_selected = _selected_color_state(before_state)
    if strategy == "page_selected":
        return after_state.get("page") == value.get("page")
    if strategy == "bound_clip_changed":
        return bool(selected) and _canonical_digest(selected) != _canonical_digest(before_selected)
    if strategy == "comp_flattened":
        return native.get("flattened") is True and native.get("clip") == prepared.get("lowering", {}).get("privateTargetBinding", {}).get("selector")
    if strategy == "comp_repaired":
        return native.get("repaired") is True and native.get("clip") == prepared.get("lowering", {}).get("privateTargetBinding", {}).get("selector")
    if strategy == "node_enabled_ack":
        requested = descriptor.action_id.endswith(".enable")
        return (
            native.get("message") == f"{'Enabled' if requested else 'Disabled'} node {value.get('nodeIndex')}."
            and _rendered_frame_proof(native) is not None
        )
    if strategy == "node_reset_ack":
        return native.get("message") == "Reset all grades."
    if strategy == "node_label_set":
        nodes = selected.get("nodes", selected.get("node_graph", {}).get("nodes"))
        before_nodes = before_selected.get("nodes", before_selected.get("node_graph", {}).get("nodes"))
        return _canonical_digest(nodes) != _canonical_digest(before_nodes) and isinstance(nodes, list) and any(
            isinstance(row, Mapping)
            and row.get("index", row.get("nodeIndex")) == value.get("nodeIndex")
            and row.get("label") == value.get("label") for row in nodes
        )
    if strategy == "node_lut_set":
        nodes = selected.get("nodes", selected.get("node_graph", {}).get("nodes"))
        before_nodes = before_selected.get(
            "nodes", before_selected.get("node_graph", {}).get("nodes")
        )
        requested_path = str(value.get("lutPath") or "")
        return (
            bool(requested_path)
            and _canonical_digest(nodes) != _canonical_digest(before_nodes)
            and isinstance(nodes, list)
            and any(
                isinstance(row, Mapping)
                and row.get("index", row.get("nodeIndex")) == value.get("nodeIndex")
                and row.get("lut") == requested_path
                for row in nodes
            )
        )
    if strategy == "power_window_circle":
        verification = native.get("verification")
        window = (
            verification.get("window_verified")
            if isinstance(verification, Mapping)
            else None
        )
        def matches_number(native_key: str, input_key: str) -> bool:
            observed = verification.get(native_key) if isinstance(verification, Mapping) else None
            requested = value.get(input_key)
            return (
                isinstance(observed, (int, float))
                and not isinstance(observed, bool)
                and isinstance(requested, (int, float))
                and not isinstance(requested, bool)
                and math.isclose(float(observed), float(requested), rel_tol=0, abs_tol=1e-5)
            )
        return (
            isinstance(verification, Mapping)
            and isinstance(window, Mapping)
            and verification.get("status") == "verified"
            and verification.get("requested_node_index") == value.get("nodeIndex")
            and window.get("shape") == "circle"
            and window.get("node_index") == value.get("nodeIndex")
            and window.get("invert") is value.get("invert")
            and matches_number("size", "size")
            and matches_number("soft_1", "softness")
            and matches_number("pan", "pan")
            and matches_number("tilt", "tilt")
            and matches_number("opacity", "opacity")
        )
    if strategy == "power_window_tracked":
        readback = native.get("readback")
        before_track = readback.get("before") if isinstance(readback, Mapping) else None
        after_track = readback.get("after") if isinstance(readback, Mapping) else None
        proof = native.get("proof")
        track_result = native.get("track_result")
        return (
            native.get("action") == "color.page.power_window_track"
            and native.get("changed") is True
            and isinstance(before_track, Mapping)
            and isinstance(after_track, Mapping)
            and before_track.get("clip_id") == after_track.get("clip_id")
            and before_track.get("version_id") == after_track.get("version_id")
            and (
                before_track.get("body_sha256") != after_track.get("body_sha256")
                or before_track.get("proto_sha256") != after_track.get("proto_sha256")
            )
            and isinstance(track_result, Mapping)
            and track_result.get("direction") == value.get("direction")
            and isinstance(proof, Mapping)
            and proof.get("capture_scope") == "resolve_window"
            and isinstance(proof.get("bytes"), int)
            and proof.get("bytes", 0) > 0
            and isinstance(proof.get("window_id"), int)
            and proof.get("window_id", 0) > 0
        )
    if strategy == "window_ellipse_added":
        geometry = native.get("geometry")
        requested_center = value.get("center")
        observed_center = geometry.get("center") if isinstance(geometry, Mapping) else None
        return (
            _canonical_digest(selected) != _canonical_digest(before_selected)
            and native.get("type") == "EllipseMask"
            and native.get("shape") == "ellipse"
            and isinstance(native.get("name"), str)
            and bool(native["name"])
            and isinstance(geometry, Mapping)
            and isinstance(requested_center, (list, tuple))
            and len(requested_center) == 3
            and isinstance(observed_center, (list, tuple))
            and len(observed_center) == 2
            and all(
                math.isclose(float(observed), float(requested), rel_tol=0, abs_tol=1e-5)
                for observed, requested in zip(observed_center, requested_center[:2])
            )
            and all(
                isinstance(geometry.get(field), (int, float))
                and not isinstance(geometry.get(field), bool)
                and math.isclose(float(geometry[field]), float(value[field]), rel_tol=0, abs_tol=1e-5)
                for field in ("width", "height", "softness")
            )
            and isinstance(native.get("validation"), Mapping)
            and native["validation"].get("valid") is True
        )
    if strategy == "tracker_added":
        requested_center = value.get("patternCenter")
        observed_center = native.get("pattern_center")
        return (
            _canonical_digest(selected) != _canonical_digest(before_selected)
            and native.get("type") == "Tracker"
            and isinstance(native.get("name"), str)
            and bool(native["name"])
            and isinstance(requested_center, (list, tuple))
            and len(requested_center) == 3
            and isinstance(observed_center, (list, tuple))
            and len(observed_center) == 2
            and all(
                math.isclose(float(observed), float(requested), rel_tol=0, abs_tol=1e-5)
                for observed, requested in zip(observed_center, requested_center[:2])
            )
            and isinstance(native.get("validation"), Mapping)
            and native["validation"].get("valid") is True
        )
    if strategy == "node_cache_set":
        cache = semantic.get("nodeCache") if isinstance(semantic, Mapping) else None
        before_cache = before_semantic.get("nodeCache") if isinstance(before_semantic, Mapping) else None
        return _canonical_digest(cache) != _canonical_digest(before_cache) and isinstance(cache, Mapping) and cache.get("cache_mode") == value.get("cacheMode")
    versions = selected.get("versions")
    version_present = isinstance(versions, list) and any(
        isinstance(row, Mapping)
        and row.get("name") == value.get("name")
        and row.get("type", row.get("versionType")) == value.get("versionType") for row in versions
    )
    if strategy == "version_created":
        return version_present and _canonical_digest(versions) != _canonical_digest(before_selected.get("versions"))
    if strategy == "version_deleted":
        return not version_present and _canonical_digest(versions) != _canonical_digest(before_selected.get("versions"))
    if strategy == "version_loaded":
        return native.get("name") == value.get("name") and native.get("version_type", native.get("versionType")) == value.get("versionType") and native.get("loaded") is True and native.get("active_after_load") is not False
    groups = semantic.get("groups") if isinstance(semantic, Mapping) else None
    before_groups = before_semantic.get("groups") if isinstance(before_semantic, Mapping) else None
    group_name = _selector_name(prepared, value.get("groupId"))
    if strategy == "group_created":
        return _rows_have(groups, "name", value.get("name")) and not _rows_have(before_groups, "name", value.get("name"))
    if strategy == "group_deleted":
        return group_name is not None and _rows_have(before_groups, "name", group_name) and not _rows_have(groups, "name", group_name)
    if strategy == "group_renamed":
        return _rows_have(before_groups, "name", group_name) and _rows_have(groups, "name", value.get("newName")) and not _rows_have(groups, "name", group_name)
    color_group = selected.get("color_group")
    before_color_group = before_selected.get("color_group")
    current_group = color_group.get("group_name") if isinstance(color_group, Mapping) else None
    prior_group = before_color_group.get("group_name") if isinstance(before_color_group, Mapping) else None
    if strategy == "clip_group_assigned":
        return group_name is not None and current_group == group_name and prior_group != current_group
    if strategy == "clip_group_removed":
        return prior_group is not None and current_group is None
    albums = semantic.get("albums") if isinstance(semantic, Mapping) else None
    before_albums = before_semantic.get("albums") if isinstance(before_semantic, Mapping) else None
    album_name = _selector_name(prepared, value.get("albumId"))
    if strategy == "album_created":
        return _rows_have(albums, "name", value.get("name")) and not _rows_have(before_albums, "name", value.get("name"))
    if strategy == "album_renamed":
        return _rows_have(before_albums, "name", album_name) and _rows_have(albums, "name", value.get("newName")) and not _rows_have(albums, "name", album_name)
    if strategy == "album_selected":
        current = semantic.get("currentAlbum") if isinstance(semantic, Mapping) else None
        return album_name is not None and isinstance(current, Mapping) and current.get("name") == album_name
    if strategy == "still_deleted":
        return native.get("deleted") is True and native.get("verified") is True and native.get("selector") == _selector_name(prepared, value.get("stillId"))
    if strategy == "still_grabbed":
        return native.get("grabbed") is True and native.get("verified") is True and isinstance(native.get("created_count"), int) and native["created_count"] > 0
    if strategy == "still_imported":
        custody = prepared.get("lowering", {}).get("artifactCustody", {}).get(value.get("sourceArtifactId"), {})
        return native.get("path") == custody.get("path") and native.get("album") == (_selector_name(prepared, value.get("albumId")) or "current")
    if strategy == "still_labeled":
        return native.get("verified") is True and native.get("updated") is True and native.get("label") == value.get("label") and native.get("readback_label") == value.get("label")
    if strategy == "power_grade_album_created":
        before_albums = before_semantic.get("powerGradeAlbums", [])
        after_albums = semantic.get("powerGradeAlbums", [])
        return (
            native.get("name") == value.get("name")
            and native.get("power_grade") is True
            and value.get("name") not in before_albums
            and value.get("name") in after_albums
        )
    return False


def _rendered_frame_proof(native_result: Any) -> Mapping[str, Any] | None:
    if not isinstance(native_result, Mapping):
        return None
    proof = native_result.get("render_proof", native_result.get("renderProof"))
    if not isinstance(proof, Mapping):
        verification = native_result.get("verification")
        proof = verification if isinstance(verification, Mapping) else None
    if not isinstance(proof, Mapping) or proof.get("status") != "verified":
        return None
    comparison = proof.get("comparison")
    changed_pixels = (
        comparison.get("changed_pixel_count", comparison.get("changedPixelCount"))
        if isinstance(comparison, Mapping)
        else None
    )
    if not isinstance(changed_pixels, int) or changed_pixels < 1:
        return None
    paths: list[Path] = []
    for key in ("before", "after", "final_composite"):
        record = proof.get(key)
        path_text = record.get("path") if isinstance(record, Mapping) else None
        if isinstance(path_text, str) and Path(path_text).is_absolute():
            paths.append(Path(path_text))
    if len(paths) < 2 or any(not path.is_file() for path in paths):
        return None
    hashes = [
        {"sha256": _file_sha256(path)[0], "byteLength": _file_sha256(path)[1]}
        for path in paths
    ]
    return {
        "status": "verified",
        "evidenceDigest": _kernel_digest(
            "execution", {"changedPixelCount": changed_pixels, "frames": hashes}
        ),
    }


def _handler_default(parameter: inspect.Parameter) -> Any:
    default = parameter.default
    if default is inspect.Parameter.empty:
        raise InventoryValidationError("Color handler requires an unbound private parameter")
    typer_default = getattr(default, "default", inspect.Parameter.empty)
    return typer_default if typer_default is not inspect.Parameter.empty else default


def _handler_arguments(
    descriptor: ColorActionDescriptor,
    value: Mapping[str, Any],
    prepared: Mapping[str, Any],
    handler: Any,
) -> dict[str, Any]:
    signature = inspect.signature(handler)
    available = set(signature.parameters)
    arguments: dict[str, Any] = {}
    target_binding = prepared.get("lowering", {}).get("privateTargetBinding")
    selector = target_binding.get("selector") if isinstance(target_binding, Mapping) else None
    artifacts = prepared.get("lowering", {}).get("privateManagedArtifacts")
    selectors = prepared.get("lowering", {}).get("privateSelectorBindings")

    def assign(name: str, item: Any) -> None:
        if name in available:
            arguments[name] = item

    for field_name, binding in descriptor.private_bindings:
        item = value.get(field_name)
        if binding in {"prepared_guard", "managed_artifact"}:
            continue
        if binding == "resolved_target":
            if field_name == "timelineItemId":
                assign("clip_name", selector)
                assign("clip", selector)
            elif field_name in {"groupId", "albumId", "stillId"}:
                record = selectors.get(item) if isinstance(selectors, Mapping) else None
                native_selector = record.get("selector") if isinstance(record, Mapping) else None
                for name in ("group", "group_name", "album", "still", "selector"):
                    assign(name, native_selector)
            elif field_name == "trackIndex":
                assign("track", item)
            elif field_name == "recordFrame":
                assign("at", item)
                assign("record_frame", item)
            continue
        if binding.startswith("artifact:"):
            record = artifacts.get(item) if isinstance(artifacts, Mapping) else None
            path = record.get("path") if isinstance(record, Mapping) else None
            if not isinstance(path, str) or not Path(path).is_absolute():
                raise InventoryValidationError("Color managed artifact is unavailable")
            assign(binding.split(":", 1)[1], path)
            continue
        if binding.startswith(("resolved_group:", "resolved_album:", "resolved_still:")):
            record = selectors.get(item) if isinstance(selectors, Mapping) else None
            native_selector = record.get("selector") if isinstance(record, Mapping) else None
            if not isinstance(native_selector, str) or not native_selector:
                raise InventoryValidationError("Color named target is not exactly bound")
            assign(binding.split(":", 1)[1], native_selector)
            continue
        if binding.startswith("resolved_selector:"):
            record = selectors.get(item) if isinstance(selectors, Mapping) else None
            native_selector = record.get("selector") if isinstance(record, Mapping) else None
            if not isinstance(native_selector, str) or not native_selector:
                raise InventoryValidationError("Color snapshot selector is not exactly bound")
            assign(binding.split(":", 1)[1], native_selector)
            continue
        if binding.startswith("resolved_clip:"):
            assign(binding.split(":", 1)[1], selector)
            continue
        if binding.startswith("enum_remote:"):
            assign(binding.split(":", 1)[1], item == "remote")
            continue
        if binding.startswith("version_add_name:"):
            assign(binding.split(":", 1)[1], item)
            continue
        if (
            descriptor.action_id == "cutagent.action.color.page.magic_mask_refine"
            and field_name == "stroke"
        ):
            if not isinstance(item, list) or not item:
                raise InventoryValidationError("Magic Mask stroke must contain normalized points")
            points: list[str] = []
            for point in item:
                if (
                    not isinstance(point, list)
                    or len(point) != 3
                    or any(
                        isinstance(component, bool)
                        or not isinstance(component, (int, float))
                        or not math.isfinite(float(component))
                        or float(component) < 0.0
                        or float(component) > 1.0
                        for component in point
                    )
                ):
                    raise InventoryValidationError(
                        "Magic Mask stroke points must be normalized finite x/y/pressure triples"
                    )
                # The reviewed GUI route owns a path-only stroke. Pressure is
                # validated for contract truth but is not an exposed GUI input.
                points.append(f"{float(point[0]):.17g},{float(point[1]):.17g}")
            assign(binding, ";".join(points))
            continue
        if binding.startswith("components:"):
            names = binding.split(":", 1)[1].split(",")
            components = item.values() if isinstance(item, Mapping) else item
            if not isinstance(components, (list, tuple)) or len(components) != len(names):
                raise InventoryValidationError("Color component lowering is incomplete")
            for name, component in zip(names, components):
                assign(name, component)
            continue
        if binding.startswith("cdl_triplet:"):
            if (
                not isinstance(item, (list, tuple))
                or len(item) != 3
                or any(
                    isinstance(component, bool)
                    or not isinstance(component, (int, float))
                    or not math.isfinite(float(component))
                    for component in item
                )
            ):
                raise InventoryValidationError(
                    "CDL triplets must contain exactly three finite numeric values"
                )
            assign(
                binding.split(":", 1)[1],
                " ".join(f"{float(component):.17g}" for component in item),
            )
            continue
        if binding.startswith("xy_pair:"):
            if (
                not isinstance(item, (list, tuple))
                or len(item) != 3
                or any(
                    isinstance(component, bool)
                    or not isinstance(component, (int, float))
                    or not math.isfinite(float(component))
                    for component in item
                )
            ):
                raise InventoryValidationError(
                    "Color coordinate triplets must contain exactly three finite numeric values"
                )
            assign(
                binding.split(":", 1)[1],
                ",".join(f"{float(component):.17g}" for component in item[:2]),
            )
            continue
        if binding == "softness_to_all_channels":
            for name in ("soft_1", "soft_2", "soft_3", "soft_4"):
                assign(name, item)
            continue
        if binding == "select_verified_node_then_handler":
            assign("node_index", item)
            continue
        assign(binding, item)
    for name, parameter in signature.parameters.items():
        if name not in arguments:
            arguments[name] = True if name == "force" else _handler_default(parameter)
    return arguments


def _invoke_bound_handler(
    descriptor: ColorActionDescriptor,
    value: Mapping[str, Any],
    prepared: Mapping[str, Any],
) -> Any:
    if descriptor.command_id == "page.switch":
        from ..commands import page as command_module
    else:
        from ..commands import color as command_module

    handler = inspect.unwrap(getattr(command_module, descriptor.lowering_profile.split(":", 1)[1]))
    arguments = _handler_arguments(descriptor, value, prepared, handler)
    captured_output: list[Any] = []
    captured_success: list[Any] = []
    globals_map = handler.__globals__
    previous_output = globals_map.get("output")
    previous_success = globals_map.get("success")
    previous_policy = globals_map.get("enforce_mutation_policy")
    globals_map["output"] = lambda data, **_options: captured_output.append(deepcopy(data))
    globals_map["success"] = lambda message, **_options: captured_success.append(
        {"message": str(message)}
    )
    if descriptor.operation_class == "mutation":
        globals_map["enforce_mutation_policy"] = lambda *_args, **_options: {
            "capability_id": descriptor.capability_id,
            "capability_status": descriptor.capability_status,
        }
    try:
        returned = handler(**arguments)
    finally:
        if previous_output is None:
            globals_map.pop("output", None)
        else:
            globals_map["output"] = previous_output
        if previous_success is None:
            globals_map.pop("success", None)
        else:
            globals_map["success"] = previous_success
        if previous_policy is None:
            globals_map.pop("enforce_mutation_policy", None)
        else:
            globals_map["enforce_mutation_policy"] = previous_policy
    if len(captured_output) > 1:
        raise InventoryValidationError("Color handler emitted more than one authoritative result")
    result = (
        captured_output[0]
        if captured_output
        else returned
        if returned is not None
        else captured_success[-1]
        if captured_success
        else None
    )
    if result is None:
        raise InventoryValidationError("Color handler returned no typed result")
    return result


def _stable_targets(
    descriptor: ColorActionDescriptor,
    value: Mapping[str, Any],
    context: Mapping[str, Any],
    revision: str,
) -> list[dict[str, Any]]:
    if not isinstance(revision, str) or not revision:
        raise InventoryValidationError("Color action has no stable runtime revision")
    project_id = str(value.get("projectId") or context.get("project", {}).get("projectId") or "")
    if not project_id:
        raise InventoryValidationError("Color action has no stable project identity")
    targets: list[dict[str, Any]] = []
    if isinstance(value.get("timelineItemId"), str):
        binding = _target_binding(context, value["timelineItemId"], "clip")
        targets.append(
            {
                "kind": "clip",
                "stableId": value["timelineItemId"],
                "revision": revision,
                "trackType": "video",
                "trackIndex": binding["trackIndex"],
            }
        )
    elif any(isinstance(value.get(field_name), str) for field_name in ("stillId", "albumId", "groupId")):
        stable_id = next(
            value[field_name]
            for field_name in ("stillId", "albumId", "groupId")
            if isinstance(value.get(field_name), str)
        )
        targets.append({"kind": "media", "stableId": stable_id, "revision": revision})
    else:
        targets.append({"kind": "project", "stableId": project_id, "revision": revision})
    if descriptor.action_id == "cutagent.action.color.grade_copy":
        # Exact multi-target clips are supplied by the session's private bindings.
        targets = [
            {"kind": "clip", "stableId": binding["stableId"], "revision": revision}
            for name in [value["sourceClipName"], *value["targetClipNames"]]
            for binding in [_named_clip_binding(context, name)]
        ]
    if descriptor.action_id == "cutagent.action.color.still.grab_all":
        item_ids = context.get("privateAllTimelineItemIds")
        if not isinstance(item_ids, list) or not item_ids:
            raise InventoryValidationError("Color grab-all requires a closed timeline-item inventory")
        targets = [{"kind": "clip", "stableId": stable_id, "revision": revision} for stable_id in item_ids]
    selector_records = context.get("privateSelectorBindings")
    if isinstance(selector_records, Mapping):
        selector_fields = ["clipName", "sourceClipName", "targetClipNames", "stillSelector", "qualifierName", "trackerName", "versionName", "windowName"]
        if descriptor.action_id.startswith("cutagent.action.color.version.") and descriptor.action_id not in {
            "cutagent.action.color.version.add",
            "cutagent.action.color.version.duplicate",
        }:
            selector_fields.append("name")
        for field_name in selector_fields:
            selected = value.get(field_name)
            values = selected if isinstance(selected, list) else [selected]
            for selector in values:
                record = selector_records.get(selector) if isinstance(selector, str) else None
                if not isinstance(record, Mapping):
                    continue
                stable_id = record.get("stableId")
                kind = record.get("kind")
                if isinstance(stable_id, str) and kind in {"clip", "media", "fusion_composition"}:
                    targets.append({"kind": kind, "stableId": stable_id, "revision": revision})
    deduplicated: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for target in targets:
        key = (target["kind"], target["stableId"])
        if key not in seen:
            seen.add(key)
            deduplicated.append(target)
    targets = deduplicated
    exact = context.get("exactRequestBinding")
    if isinstance(exact, Mapping):
        identities = exact.get("identities")
        revisions = exact.get("revisions")
        target_ids = identities.get("targetIds") if isinstance(identities, Mapping) else None
        target_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
        if (
            not isinstance(target_ids, list)
            or not target_ids
            or any(not isinstance(stable_id, str) or not stable_id for stable_id in target_ids)
            or len(set(target_ids)) != len(target_ids)
            or not isinstance(target_revisions, Mapping)
            or set(target_revisions) != set(target_ids)
            or any(
                not isinstance(target_revisions.get(stable_id), str)
                or not target_revisions[stable_id]
                for stable_id in target_ids
            )
        ):
            raise InventoryValidationError("Color signed target inventory is incomplete")
        candidates = {target["stableId"]: target for target in targets}
        for bindings_key in (
            "privateTargetBindings", "privateSelectorBindings",
            "privateNamedClipBindings",
        ):
            bindings = context.get(bindings_key)
            if not isinstance(bindings, Mapping):
                continue
            for binding_key, binding in bindings.items():
                if not isinstance(binding, Mapping):
                    continue
                stable_id = binding.get("stableId", binding_key)
                kind = binding.get("kind")
                if stable_id not in target_ids or kind not in {
                    "clip", "media", "fusion_composition",
                }:
                    continue
                candidate = {"kind": kind, "stableId": stable_id}
                if kind == "clip":
                    candidate.update({
                        "trackType": "video",
                        "trackIndex": binding.get("trackIndex"),
                    })
                candidates[stable_id] = candidate
        managed_artifacts = context.get("privateManagedArtifacts")
        if isinstance(managed_artifacts, Mapping):
            for artifact_id in managed_artifacts:
                if artifact_id in target_ids:
                    candidates[artifact_id] = {
                        "kind": "artifact", "stableId": artifact_id,
                    }
        if project_id in target_ids:
            candidates[project_id] = {"kind": "project", "stableId": project_id}
        if any(stable_id not in candidates for stable_id in target_ids):
            raise InventoryValidationError("Color signed target has no private binding")
        targets = [
            {**candidates[stable_id], "revision": target_revisions[stable_id]}
            for stable_id in target_ids
        ]
    return targets


def _named_clip_binding(context: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    bindings = context.get("privateNamedClipBindings")
    binding = bindings.get(name) if isinstance(bindings, Mapping) else None
    if not isinstance(binding, Mapping) or not isinstance(binding.get("stableId"), str):
        raise InventoryValidationError("Color named clip selection is not exactly bound")
    return binding


def _timeline_items(summary: Any) -> list[Mapping[str, Any]]:
    if not isinstance(summary, Mapping):
        return []
    rows: list[Mapping[str, Any]] = []
    for track in summary.get("tracks", ()):
        if isinstance(track, Mapping) and track.get("type") == "video":
            rows.extend(item for item in track.get("items", ()) if isinstance(item, Mapping))
    return rows


def _derive_current_clip_binding(
    stable_id: str,
    summary: Any,
    color_state: Any,
) -> dict[str, Any]:
    target = color_state.get("target") if isinstance(color_state, Mapping) else None
    native_id = target.get("timeline_item_unique_id") if isinstance(target, Mapping) else None
    selector = target.get("name") if isinstance(target, Mapping) else None
    matches: list[tuple[int, Mapping[str, Any]]] = []
    if isinstance(summary, Mapping):
        for track in summary.get("tracks", ()):
            if not isinstance(track, Mapping) or track.get("type") != "video":
                continue
            track_index = track.get("index")
            if not isinstance(track_index, int) or isinstance(track_index, bool) or track_index < 1:
                continue
            for item in track.get("items", ()):
                if isinstance(item, Mapping) and item.get("timeline_item_unique_id") == native_id:
                    matches.append((track_index, item))
    if (
        not isinstance(native_id, str)
        or not native_id
        or not isinstance(selector, str)
        or not selector
        or len(matches) != 1
        or matches[0][1].get("name") != selector
    ):
        raise InventoryValidationError("Current Color clip identity cannot be bound exactly")
    return {
        "kind": "clip",
        "selector": selector,
        "nativeId": native_id,
        "trackIndex": matches[0][0],
        "stableId": stable_id,
    }


def _bound_clip_selectors(
    context: Mapping[str, Any],
    value: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    bindings: list[Mapping[str, Any]] = []
    timeline_item_id = value.get("timelineItemId")
    if isinstance(timeline_item_id, str):
        bindings.append(_target_binding(context, timeline_item_id, "clip"))
    selectors = context.get("privateSelectorBindings")
    for field_name in ("clipName", "sourceClipName", "targetClipNames"):
        selected = value.get(field_name)
        values = selected if isinstance(selected, list) else [selected]
        for selector in values:
            record = selectors.get(selector) if isinstance(selectors, Mapping) and isinstance(selector, str) else None
            if isinstance(record, Mapping) and record.get("kind") == "clip":
                bindings.append(record)
    unique: dict[tuple[str, str], Mapping[str, Any]] = {}
    for binding in bindings:
        selector = binding.get("selector")
        native_id = binding.get("nativeId")
        if not isinstance(selector, str) or not isinstance(native_id, str):
            raise InventoryValidationError("Color clip binding lacks exact native identity")
        unique[(selector, native_id)] = binding
    return tuple(unique.values())


@dataclass
class ColorPreparedActionRuntime:
    """Concrete DaVinci Resolve inspector, executor, and checkpoint recovery adapter."""

    checkpoints: dict[str, str] = field(default_factory=dict)

    def inspect(self, context: Mapping[str, Any], descriptor: ColorActionDescriptor, value: Mapping[str, Any]) -> dict[str, Any]:
        conn = get_connection(
            require_project=True,
            require_timeline="timelineId" in descriptor.target_fields,
        )
        _revalidate_snapshot_selectors(conn, context, descriptor, value)
        page_before = None
        if descriptor.action_id == "cutagent.action.page.switch":
            page_before = str(conn.resolve.GetCurrentPage() or "").lower()
        operation = "color.current" if "timelineId" in descriptor.target_fields else "project.context"
        node_stack_layer_index = int(value.get("nodeStackLayerIndex", 1))
        raw = timeline_ops.inspect_sdk_live_state(
            conn,
            operation,
            deadline_at_ms=_deadline(context),
            **({"node_stack_layer_index": node_stack_layer_index} if operation == "color.current" else {}),
        )
        if descriptor.action_id == "cutagent.action.page.switch":
            page_after = str(conn.resolve.GetCurrentPage() or "").lower()
            if not page_before or page_after != page_before:
                raise InventoryValidationError("DaVinci Resolve page changed during inspection")
        if raw.get("before") != raw.get("after"):
            raise InventoryValidationError("DaVinci Resolve identity changed during Color inspection")
        if operation == "color.current" and (
            raw.get("summary_before") != raw.get("summary_after")
            or raw.get("color_before") != raw.get("color_after")
        ):
            raise InventoryValidationError("DaVinci Resolve Color state changed during inspection")
        verification_phase = context.get("privateColorInspectionPhase") == "verification"
        if operation == "color.current" and descriptor.operation_class == "mutation" and not verification_phase:
            expected_guard = context.get("timeline", {}).get("mutationGuard")
            observed_guard = raw.get("mutation_guard")
            if (
                not isinstance(expected_guard, str)
                or _COLOR_GUARD_PATTERN.fullmatch(expected_guard) is None
                or not isinstance(observed_guard, str)
                or _COLOR_GUARD_PATTERN.fullmatch(observed_guard) is None
            ):
                raise InventoryValidationError("Color captured mutation guard is unavailable")
            if observed_guard != expected_guard:
                raise InventoryValidationError("Color captured mutation guard is stale")
        effective_context = deepcopy(dict(context))
        selected_color: dict[str, Any] = {}
        semantic_readback: dict[str, Any] = {}
        derived_binding: Mapping[str, Any] | None = None
        if operation == "color.current":
            stable_id = value.get("timelineItemId")
            if not isinstance(stable_id, str):
                raise InventoryValidationError("Color action lacks an exact public clip identity")
            derived_binding = _derive_current_clip_binding(
                stable_id,
                raw.get("summary_after"),
                raw.get("color_after"),
            )
            supplied = _target_binding(context, stable_id, "clip")
            if any(
                supplied.get(key) != derived_binding.get(key)
                for key in ("selector", "nativeId", "trackIndex")
            ):
                raise InventoryValidationError("Color private target binding changed")
            requested_clip_name = value.get("clipName")
            if isinstance(requested_clip_name, str):
                named = context.get("privateSelectorBindings", {}).get(
                    requested_clip_name
                )
                if (
                    not isinstance(named, Mapping)
                    or named.get("stableId") != stable_id
                    or any(
                        named.get(key) != derived_binding.get(key)
                        for key in ("selector", "nativeId", "trackIndex")
                    )
                ):
                    raise InventoryValidationError(
                        "Color clip name does not identify the bound timeline item"
                    )
            effective_context["privateTargetBindings"] = {stable_id: dict(supplied)}
            items = _timeline_items(raw.get("summary_after"))
            for binding in _bound_clip_selectors(effective_context, value):
                selector = binding["selector"]
                native_id = binding["nativeId"]
                named = [item for item in items if item.get("name") == selector]
                if len(named) != 1 or named[0].get("timeline_item_unique_id") != native_id:
                    raise InventoryValidationError("Color clip selector is ambiguous or changed")
                node_stack_layer_index = int(value.get("nodeStackLayerIndex", 1))
                before_selected = color_ops.inspect_color(
                    conn, selector, node_stack_layer_index=node_stack_layer_index
                )
                conn.refresh()
                after_selected = color_ops.inspect_color(
                    conn, selector, node_stack_layer_index=node_stack_layer_index
                )
                if before_selected != after_selected:
                    raise InventoryValidationError("Selected Color target changed during inspection")
                selected_color[native_id] = after_selected
            if descriptor.action_id.startswith("cutagent.action.color.group."):
                semantic_readback["groups"] = color_ops.list_color_groups(conn)
            if descriptor.action_id.startswith("cutagent.action.color.gallery."):
                album_selector = _gallery_album_inspection_selector(
                    context,
                    descriptor,
                    value,
                    verification_phase=verification_phase,
                )
                semantic_readback.update({
                    "albums": color_ops.list_gallery_albums(conn),
                    "currentAlbum": color_ops.get_current_album_info(conn),
                    "stills": gallery_ops.list_stills(conn, album=album_selector),
                })
            if descriptor.action_id == "cutagent.action.color.node.cache":
                semantic_readback["nodeCache"] = color_ops.get_node_cache_mode(
                    conn, str(derived_binding["selector"]), int(value["nodeIndex"]),
                    node_stack_layer_index=int(value.get("nodeStackLayerIndex", 1)),
                )
            if descriptor.action_id == "cutagent.action.color.power_grade.album.create":
                semantic_readback["powerGradeAlbums"] = _power_grade_album_names(conn)
        elif descriptor.action_id.startswith("cutagent.action.color.group."):
            semantic_readback["groups"] = color_ops.list_color_groups(conn)
        elif descriptor.action_id.startswith("cutagent.action.color.gallery."):
            album_selector = _gallery_album_inspection_selector(
                context,
                descriptor,
                value,
                verification_phase=verification_phase,
            )
            semantic_readback.update({
                "albums": color_ops.list_gallery_albums(conn),
                "currentAlbum": color_ops.get_current_album_info(conn),
                "stills": gallery_ops.list_stills(conn, album=album_selector),
            })
        elif descriptor.action_id == "cutagent.action.color.power_grade.album.create":
            semantic_readback["powerGradeAlbums"] = _power_grade_album_names(conn)

        expected_revision = (
            context.get("timeline", {}).get("timelineRevision")
            if "timelineId" in descriptor.target_fields
            else context.get("project", {}).get("projectRevision")
        )
        primary_stable_id = (
            value.get("timelineItemId")
            or value.get("stillId")
            or value.get("albumId")
            or value.get("groupId")
            or value.get("projectId")
        )
        exact_request_binding = context.get("exactRequestBinding")
        captured_target_revision = (
            exact_request_binding.get("revisions", {}).get("targets", {}).get(primary_stable_id)
            if isinstance(exact_request_binding, Mapping)
            else None
        )
        if isinstance(exact_request_binding, Mapping) and not isinstance(captured_target_revision, str):
            raise InventoryValidationError("Color signed target revision is unavailable")
        revision = captured_target_revision or value.get(descriptor.revision_field)
        if verification_phase and descriptor.operation_class == "mutation":
            observed_guard = raw.get("mutation_guard")
            if not isinstance(observed_guard, str) or _COLOR_GUARD_PATTERN.fullmatch(observed_guard) is None:
                raise InventoryValidationError("Color post-execution revision evidence is unavailable")
            revision = f"revision_color_{observed_guard.removeprefix('sha256:')}"
        elif revision is None:
            revision = expected_revision
        if not verification_phase and descriptor.operation_class == "mutation":
            _assert_color_request_revision_current(
                context, descriptor, value, expected_revision
            )
        targets = _stable_targets(descriptor, value, effective_context, revision)
        selector_bindings: dict[str, str] = {}
        private_bindings = context.get("privateTargetBindings")
        if isinstance(private_bindings, Mapping):
            for stable_id, binding in private_bindings.items():
                if isinstance(binding, Mapping) and isinstance(binding.get("selector"), str):
                    selector_bindings[binding["selector"]] = str(stable_id)
        private_selectors = context.get("privateSelectorBindings")
        if isinstance(private_selectors, Mapping):
            for selector, binding in private_selectors.items():
                if isinstance(selector, str) and isinstance(binding, Mapping) and isinstance(binding.get("stableId"), str):
                    selector_bindings[selector] = binding["stableId"]
        pre_state = {
            "identity": raw["after"],
            "timeline": raw.get("summary_after"),
            "color": raw.get("color_after"),
            "selectedColor": selected_color,
            "semanticReadback": semantic_readback,
            **({"page": page_before} if page_before is not None else {}),
        }
        return {
            **{field_name: value[field_name] for field_name in descriptor.target_fields},
            "revision": revision,
            "preState": pre_state,
            "resolvedTargets": targets,
            "resolvedTargetCount": len(targets),
            "resolvedTargetsDigest": _bound_digest(_kernel_digest, "targets", targets),
            "impactComplete": True,
            "closedComposition": True,
            "selectorResolutionComplete": True,
            "selectorBindings": selector_bindings,
            "allTimelineItemIds": [target["stableId"] for target in targets if target["kind"] == "clip"],
            "mutationGuard": raw.get("mutation_guard"),
            "privateTargetBinding": deepcopy(dict(derived_binding)) if derived_binding is not None else None,
        }

    def execute(
        self,
        context: Mapping[str, Any],
        descriptor: ColorActionDescriptor,
        prepared: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        value: Mapping[str, Any] = prepared["lowering"]["normalizedInput"]
        execution_id = str(context["executionId"])
        artifact_custody = prepared.get("lowering", {}).get("artifactCustody", {})
        if not isinstance(artifact_custody, Mapping):
            raise InventoryValidationError("Color artifact custody is invalid")
        _revalidate_artifact_custody(artifact_custody)

        def completed(native_result: Any, *, checkpoint_created: bool) -> Mapping[str, Any]:
            artifact_evidence = _destination_artifact_evidence(artifact_custody)
            return {
                "nativeResult": native_result,
                "checkpointCreated": checkpoint_created,
                **({"artifactEvidence": artifact_evidence} if artifact_evidence else {}),
            }

        guard = prepared.get("lowering", {}).get("mutationGuard")
        if descriptor.operation_class == "mutation" and (
            not isinstance(guard, str) or _COLOR_GUARD_PATTERN.fullmatch(guard) is None
        ):
            raise InventoryValidationError("Color action has no exact executable mutation guard")
        direct_node_action = descriptor.action_id in {
            "cutagent.action.color.node.label_get",
            "cutagent.action.color.node.label_set",
        }
        timeline_bound_action = "timelineId" in descriptor.target_fields
        clip_binding = prepared.get("lowering", {}).get("privateTargetBinding")
        if timeline_bound_action and (
            not isinstance(clip_binding, Mapping)
            or clip_binding.get("stableId") != value.get("timelineItemId")
            or not isinstance(clip_binding.get("selector"), str)
            or not clip_binding.get("selector")
            or not isinstance(clip_binding.get("nativeId"), str)
            or not clip_binding.get("nativeId")
            or not isinstance(clip_binding.get("trackIndex"), int)
            or isinstance(clip_binding.get("trackIndex"), bool)
            or clip_binding.get("trackIndex", 0) < 1
        ):
            raise InventoryValidationError("Prepared Color target binding is unavailable")
        clip_name = str(clip_binding["selector"]) if isinstance(clip_binding, Mapping) else ""
        requested_node_index = value.get("nodeIndex")
        node_index = (
            int(requested_node_index)
            if isinstance(requested_node_index, int)
            and not isinstance(requested_node_index, bool)
            else 0
        )
        node_stack_layer_index = value.get("nodeStackLayerIndex")
        if direct_node_action and (
            not isinstance(node_stack_layer_index, int)
            or isinstance(node_stack_layer_index, bool)
            or node_stack_layer_index < 1
        ):
            raise InventoryValidationError(
                "Prepared Color node-stack layer binding is unavailable"
            )

        def validate_bound_node_index(conn: Any) -> Any:
            if node_stack_layer_index is None:
                return color_ops.validate_node_index(conn, clip_name, node_index)
            if (
                not isinstance(node_stack_layer_index, int)
                or isinstance(node_stack_layer_index, bool)
                or node_stack_layer_index < 1
            ):
                raise InventoryValidationError(
                    "Prepared Color node-stack layer binding is invalid"
                )
            return color_ops.validate_node_index(
                conn,
                clip_name,
                node_index,
                node_stack_layer_index=node_stack_layer_index,
            )

        if descriptor.action_id == "cutagent.action.page.switch":
            with _COLOR_EXECUTION_LOCK:
                return completed(
                    _invoke_bound_handler(descriptor, value, prepared),
                    checkpoint_created=False,
                )
        if descriptor.operation_class == "read" and not direct_node_action:
            with _COLOR_EXECUTION_LOCK:
                if node_index:
                    conn = get_connection(require_timeline=True, require_project=True)
                    validate_bound_node_index(conn)
                return completed(
                    _invoke_bound_handler(descriptor, value, prepared),
                    checkpoint_created=False,
                )
        if direct_node_action and (
            not isinstance(clip_binding, Mapping)
            or clip_binding.get("stableId") != value["timelineItemId"]
        ):
            raise InventoryValidationError("Prepared Color target binding is unavailable")
        requested_label = value.get("label")
        with _COLOR_EXECUTION_LOCK:
            guard_env = (
                _COLOR_GUARD_ENV
                if "timelineId" in descriptor.target_fields
                else _PROJECT_GUARD_ENV
            )
            previous_guard = os.environ.get(guard_env)
            previous_layer_index = os.environ.get(_COLOR_NODE_STACK_LAYER_INDEX_ENV)
            if descriptor.operation_class == "mutation":
                os.environ[guard_env] = str(guard)
                if guard_env == _COLOR_GUARD_ENV:
                    os.environ[_COLOR_NODE_STACK_LAYER_INDEX_ENV] = str(
                        node_stack_layer_index or 1
                    )
            try:
                conn = get_connection(require_timeline=True, require_project=True)
                if descriptor.operation_class == "mutation":
                    _revalidate_snapshot_selectors(conn, context, descriptor, value)
                    # Check exact live state before checkpoint creation: checkpoint
                    # creation itself can persist project data.
                    if guard_env == _COLOR_GUARD_ENV:
                        timeline_ops.require_sdk_color_mutation_guard(conn)
                    else:
                        sdk_live_inspection.require_project_mutation_guard(
                            conn,
                            list_timelines=timeline_ops.list_timelines,
                        )
                    # Node indexes are positional native identities. Validate
                    # the exact guarded graph position before checkpoint
                    # creation, because checkpoint creation may persist data.
                    if node_index:
                        validate_bound_node_index(conn)
                    checkpoint = version_ops.create_checkpoint(
                        conn,
                        label=f"SDK Color recovery {execution_id}",
                        kind="before_prompt",
                        session_id=str(context.get("session", {}).get("sdkSessionId") or "sdk"),
                    )
                    self.checkpoints[execution_id] = str(checkpoint["id"])
                    if guard_env == _COLOR_GUARD_ENV:
                        _refresh_color_guard_after_checkpoint(
                            conn,
                            context,
                            descriptor,
                            clip_binding,
                            node_index,
                            int(node_stack_layer_index or 1),
                        )
                    if direct_node_action:
                        color_ops.set_node_label(
                            conn,
                            clip_name,
                            node_index,
                            str(requested_label),
                            node_stack_layer_index=node_stack_layer_index,
                        )
                        native_result: Any = {
                            "nodeIndex": node_index,
                            "label": color_ops.get_node_label(
                                conn,
                                clip_name,
                                node_index,
                                node_stack_layer_index=node_stack_layer_index,
                            ),
                        }
                    else:
                        node_enabled_action = descriptor.action_id in {
                            "cutagent.action.color.node.enable",
                            "cutagent.action.color.node.disable",
                        }
                        render_proof = None
                        if node_enabled_action:
                            from ..commands import color as color_commands

                            render_proof = color_commands._begin_color_render_proof(
                                conn,
                                clip_name=clip_name,
                                route="api_native_sdk_node_enabled_state",
                            )
                        native_result = _invoke_bound_handler(descriptor, value, prepared)
                        _persist_project_scoped_color_mutation(conn, descriptor)
                        if render_proof is not None:
                            from ..commands import color as color_commands

                            conn.refresh()
                            native_result = {
                                **(dict(native_result) if isinstance(native_result, Mapping) else {}),
                                "render_proof": color_commands._complete_color_render_proof(
                                    conn, render_proof, partial_result=native_result
                                ),
                            }
                else:
                    validate_bound_node_index(conn)
                    native_result = {
                        "nodeIndex": node_index,
                        "label": color_ops.get_node_label(
                            conn,
                            clip_name,
                            node_index,
                            node_stack_layer_index=node_stack_layer_index,
                        ),
                    }
            finally:
                if previous_guard is None:
                    os.environ.pop(guard_env, None)
                else:
                    os.environ[guard_env] = previous_guard
                if previous_layer_index is None:
                    os.environ.pop(_COLOR_NODE_STACK_LAYER_INDEX_ENV, None)
                else:
                    os.environ[_COLOR_NODE_STACK_LAYER_INDEX_ENV] = previous_layer_index
        if (
            descriptor.action_id == "cutagent.action.color.node.label_set"
            and native_result.get("label") != requested_label
        ):
            raise InventoryValidationError("Color node label write did not verify by exact readback")
        return completed(
            native_result,
            checkpoint_created=descriptor.operation_class == "mutation",
        )

    def recover(
        self,
        context: Mapping[str, Any],
        descriptor: ColorActionDescriptor,
        prepared: Mapping[str, Any],
    ) -> dict[str, Any]:
        custody = prepared.get("lowering", {}).get("artifactCustody", {})
        artifact_restored = True
        if isinstance(custody, Mapping):
            for record in custody.values():
                if not isinstance(record, Mapping):
                    artifact_restored = False
                    continue
                path = Path(str(record.get("path") or ""))
                if record.get("role") == "destination" and path.exists():
                    try:
                        if path.is_file():
                            path.unlink()
                        else:
                            artifact_restored = False
                    except OSError:
                        artifact_restored = False
                elif record.get("role") == "source":
                    expected = (record.get("sha256"), record.get("byteLength"))
                    if not path.is_file() or _file_sha256(path) != expected:
                        artifact_restored = False
        else:
            artifact_restored = False

        if descriptor.action_id == "cutagent.action.page.switch":
            previous_page = prepared.get("preState", {}).get("page")
            if not isinstance(previous_page, str) or not previous_page:
                return {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}
            try:
                conn = get_connection(require_project=False)
                restored = bool(conn.resolve.OpenPage(previous_page))
                observed = str(conn.resolve.GetCurrentPage() or "").lower()
            except Exception:
                return {"outcome": "failed", "attempted": True, "manualActionRequired": True}
            exact = restored and observed == previous_page and artifact_restored
            return {
                "outcome": "succeeded" if exact else "manual_required",
                "attempted": True,
                "manualActionRequired": not exact,
            }
        if descriptor.operation_class == "read":
            try:
                value = prepared["lowering"]["normalizedInput"]
                restored = self.inspect(context, descriptor, value)["preState"]
                exact = (
                    artifact_restored
                    and _canonical_digest(restored)
                    == _canonical_digest(prepared["preState"])
                )
            except Exception:
                exact = False
            return {
                "outcome": "succeeded" if exact else "manual_required",
                "attempted": True,
                "manualActionRequired": not exact,
            }
        execution_id = str(context.get("executionId") or "")
        checkpoint_id = self.checkpoints.get(execution_id)
        if not checkpoint_id:
            return {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}
        try:
            conn = get_connection(require_project=True)
            version_ops.restore_checkpoint(
                conn,
                checkpoint_id,
                session_id=str(context.get("session", {}).get("sdkSessionId") or "sdk"),
            )
        except Exception:
            return {"outcome": "failed", "attempted": True, "manualActionRequired": True}
        try:
            value = prepared["lowering"]["normalizedInput"]
            restored = self.inspect(context, descriptor, value)["preState"]
            restored_exactly = (
                artifact_restored
                and _canonical_digest(restored)
                == _canonical_digest(prepared["preState"])
            )
        except Exception:
            restored_exactly = False
        return {
            "outcome": "succeeded" if restored_exactly else "manual_required",
            "attempted": True,
            "manualActionRequired": not restored_exactly,
        }


def _kernel_digest(label: str, value: Any) -> str:
    from ..sdk_prepared_action import prepared_action_digest

    return prepared_action_digest(label, value)


def _stable_selector_id(
    prepared: Mapping[str, Any],
    selector: Any,
    *,
    prefix: str,
    ordinal: int | None = None,
) -> str:
    bindings = prepared.get("lowering", {}).get("privateSelectorBindings", {})
    record = bindings.get(str(selector)) if isinstance(bindings, Mapping) else None
    if not isinstance(record, Mapping) and isinstance(bindings, Mapping):
        matches = [candidate for candidate in bindings.values() if (
            isinstance(candidate, Mapping)
            and (
                candidate.get("selector") == selector
                or (prefix == "still_" and candidate.get("inventoryLabel", "") == (selector or ""))
            )
            and (ordinal is None or candidate.get("ordinal") == ordinal)
            and isinstance(candidate.get("stableId"), str)
            and candidate["stableId"].startswith(prefix)
        )]
        record = matches[0] if len(matches) == 1 else None
    stable_id = record.get("stableId") if isinstance(record, Mapping) else None
    if not isinstance(stable_id, str) or not stable_id.startswith(prefix):
        raise InventoryValidationError("Color result entity has no persistent stable identity")
    return stable_id


def _created_entity_ids(
    context: Mapping[str, Any], action_id: str, *, prefix: str
) -> list[str]:
    bindings = context.get("privatePostEntityIds", context.get("privateCreatedEntityIds"))
    selected = bindings.get(action_id) if isinstance(bindings, Mapping) else None
    values = selected if isinstance(selected, list) else [selected]
    result = [item for item in values if isinstance(item, str) and item.startswith(prefix)]
    if not result:
        raise InventoryValidationError("Color created entity lacks a persistent stable identity")
    return result


def _post_selector_record(
    *, collection_kind: str, ordinal: int, label: str | None, parent: Mapping[str, Any], revision: str
) -> dict[str, Any]:
    selector = str(ordinal) if collection_kind == "stills" else label
    if not isinstance(selector, str) or not selector:
        raise InventoryValidationError("Color post-mutation selector has no exact executable selector")
    record = {
        "collectionKind": collection_kind,
        "ordinal": ordinal,
        "selector": selector,
        "parent": dict(parent),
        "capturedRevision": revision,
        **({"inventoryLabel": label or ""} if collection_kind == "stills" else {}),
    }
    record["stableId"] = _snapshot_selector_id(record)
    return record


def _post_entity_ids(
    context: Mapping[str, Any], descriptor: ColorActionDescriptor,
    value: Mapping[str, Any], before: Mapping[str, Any], after: Mapping[str, Any],
) -> dict[str, list[str]]:
    state = after.get("preState")
    semantic = state.get("semanticReadback") if isinstance(state, Mapping) else None
    if not isinstance(semantic, Mapping):
        return {}
    parent = {"projectId": value.get("projectId"), "timelineId": None, "timelineItemId": None, "compositionIndex": None}
    specs: list[tuple[str, Any, str, str]] = []
    action_id = descriptor.action_id
    if action_id in {"cutagent.action.color.group.add", "cutagent.action.color.group.rename"}:
        specs.append(("groups", semantic.get("groups"), value.get("newName", value.get("name")), "group_"))
    if action_id in {"cutagent.action.color.gallery.album.create", "cutagent.action.color.gallery.album.rename"}:
        specs.append(("albums", semantic.get("albums"), value.get("newName", value.get("name")), "album_"))
    if action_id in {"cutagent.action.color.gallery.still.grab", "cutagent.action.color.gallery.still.import"}:
        current = semantic.get("currentAlbum")
        current_name = current.get("name") if isinstance(current, Mapping) else None
        specs.append(("albums", semantic.get("albums"), current_name, "album_"))
        specs.append(("stills", semantic.get("stills"), None, "still_"))
    if action_id == "cutagent.action.color.power_grade.album.create":
        specs.append(("powerGradeAlbums", [
            {"index": index, "name": name}
            for index, name in enumerate(semantic.get("powerGradeAlbums", ()), 1)
        ], value.get("name"), "album_"))
    created: list[str] = []
    reacquired_album_id: str | None = None
    for kind, rows, desired, prefix in specs:
        if not isinstance(rows, list):
            continue
        revision = _selector_inventory_revision(kind, rows)
        candidates = []
        for index, row in enumerate(rows, 1):
            if not isinstance(row, Mapping):
                continue
            label = _row_label(row)
            ordinal = row.get("index", index)
            if (not isinstance(label, str) and kind != "stills") or not isinstance(ordinal, int):
                continue
            if desired is None or label == desired:
                record = _post_selector_record(
                    collection_kind=kind, ordinal=ordinal, label=label,
                    parent={**parent, **({"albumId": value.get("albumId")} if kind == "stills" else {})},
                    revision=revision,
                )
                if record["stableId"].startswith(prefix):
                    candidates.append(record["stableId"])
        if desired is not None and len(candidates) != 1:
            raise InventoryValidationError("Color post-mutation selector could not be reacquired uniquely")
        if kind == "albums" and len(candidates) == 1:
            reacquired_album_id = candidates[0]
        if desired is None:
            before_semantic = before.get("semanticReadback") if isinstance(before, Mapping) else None
            old_rows = before_semantic.get("stills") if isinstance(before_semantic, Mapping) else None
            old_keys = {
                (row.get("index", index), _row_label(row))
                for index, row in enumerate(old_rows or (), 1) if isinstance(row, Mapping)
            }
            candidates = [
                _post_selector_record(
                    collection_kind=kind,
                    ordinal=int(row.get("index", index)),
                    label=_row_label(row),
                    parent={**parent, "albumId": value.get("albumId") or reacquired_album_id},
                    revision=revision,
                )["stableId"]
                for index, row in enumerate(rows, 1)
                if isinstance(row, Mapping)
                and (row.get("index", index), _row_label(row)) not in old_keys
            ]
            if len(candidates) != 1:
                raise InventoryValidationError("Color created still could not be reacquired uniquely")
        created.extend(candidates)
    return {action_id: created} if created else {}


def _native_rows(native_result: Any) -> list[Mapping[str, Any]]:
    if isinstance(native_result, list):
        return [item for item in native_result if isinstance(item, Mapping)]
    if isinstance(native_result, Mapping):
        for key in ("items", "versions", "groups", "clips", "albums", "stills", "nodes"):
            rows = native_result.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, Mapping)]
    return []


def _revision_change(value: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    before = value.get("revision")
    after = result.get("verifiedAfterRevision")
    if not isinstance(before, str) or not isinstance(after, str):
        raise InventoryValidationError("Color mutation lacks an independently observed revision transition")
    return {"revisionBefore": before, "revisionAfter": after, "changed": before != after}


def _exact_color_projection(
    descriptor: ColorActionDescriptor,
    context: Mapping[str, Any],
    prepared: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    value = prepared["lowering"]["normalizedInput"]
    native = result.get("nativeResult")
    native_map = native if isinstance(native, Mapping) else {}
    command = descriptor.command_id
    common = {
        key: value[key]
        for key in (
            "projectId",
            "timelineId",
            "timelineItemId",
            "nodeStackLayerIndex",
        )
        if key in value
    }
    if command == "color.node.label_get":
        body = {**common, "nodeIndex": value["nodeIndex"], "label": str(native_map.get("label", ""))}
        field = "nodeLabel"
    elif command == "color.node.lut_get":
        body = {
            **common,
            "nodeIndex": value["nodeIndex"],
            "lutPath": str(native_map.get("lut_path", native_map.get("lutPath", ""))),
        }
        field = "nodeLut"
    elif command == "color.version.list":
        body = {
            **common,
            "items": [
                {
                    "name": str(row.get("name") or ""),
                    "versionType": str(row.get("versionType", row.get("type", "local"))).lower(),
                }
                for row in _native_rows(native)
            ],
        }
        field = "versions"
    elif command == "color.group.list":
        body = {
            **common,
            "items": [
                {
                    "groupId": _stable_selector_id(prepared, row.get("name"), prefix="group_", ordinal=int(row.get("index", index))),
                    "index": int(row.get("index", index)),
                    "name": str(row.get("name") or ""),
                }
                for index, row in enumerate(_native_rows(native), 1)
            ],
        }
        field = "groups"
    elif command == "color.group.clips":
        body = {
            **common,
            "groupId": value["groupId"],
            "clips": [
                {
                    "timelineItemId": _stable_selector_id(
                        prepared, row.get("name"), prefix="timeline_item_"
                    ),
                    "index": int(row.get("index", index)),
                    "name": str(row.get("name") or ""),
                }
                for index, row in enumerate(_native_rows(native), 1)
            ],
        }
        field = "membership"
    elif command == "color.group.graph":
        nodes = native_map.get("nodes")
        body = {
            **common,
            "groupId": value["groupId"],
            "stage": value["stage"],
            "nodeCount": int(native_map.get("node_count", len(nodes) if isinstance(nodes, list) else 0)),
        }
        field = "graph"
    elif command == "color.node.list":
        body = {
            **common,
            "items": [
                {
                    "nodeIndex": int(row.get("nodeIndex", row.get("index", index))),
                    "label": str(row.get("label") or ""),
                    "lutPath": str(row.get("lutPath", row.get("lut", ""))),
                    "cacheMode": row.get("cacheMode", row.get("cache_mode")),
                    "cacheModeName": str(row.get("cacheModeName", row.get("cache_name", ""))),
                }
                for index, row in enumerate(_native_rows(native), 1)
            ],
        }
        field = "nodes"
    elif command == "color.gallery.album.list":
        body = {
            **common,
            "items": [
                {
                    "albumId": _stable_selector_id(prepared, row.get("name"), prefix="album_", ordinal=int(row.get("index", index))),
                    "index": int(row.get("index", index)),
                    "name": str(row.get("name") or ""),
                }
                for index, row in enumerate(_native_rows(native), 1)
            ],
        }
        field = "albums"
    elif command == "color.gallery.album.current":
        name = native_map.get("name", native_map.get("album"))
        body = {
            **common,
            "albumId": _stable_selector_id(prepared, name, prefix="album_", ordinal=int(native_map.get("index", 1))),
            "index": int(native_map.get("index", 1)),
            "name": str(name or ""),
        }
        field = "album"
    elif command == "color.gallery.still.list":
        body = {
            **common,
            "albumId": value["albumId"],
            "items": [
                {
                    "stillId": _stable_selector_id(
                        prepared, row.get("label", row.get("name")), prefix="still_", ordinal=int(row.get("index", index))
                    ),
                    "index": int(row.get("index", index)),
                    "label": str(row.get("label") or ""),
                }
                for index, row in enumerate(_native_rows(native), 1)
            ],
        }
        field = "stills"
    elif command == "color.gallery.still.export":
        evidence = result.get("artifactEvidence")
        artifact = evidence[0] if isinstance(evidence, list) and evidence else None
        if not isinstance(artifact, Mapping):
            raise InventoryValidationError("Color exported still lacks artifact readback")
        body = {
            **common,
            "albumId": value["albumId"],
            "stillId": value["stillId"],
            "format": value["format"],
            "artifactId": artifact["artifactId"],
            "exists": True,
            "byteCount": artifact["byteLength"],
        }
        field = "exportedStill"
    else:
        revision = _revision_change(value, result)
        mutation = {**common, "revision": revision, "verified": True}
        if command.startswith("color.version."):
            operation = command.rsplit(".", 1)[1]
            body = {**mutation, "name": value["name"], "versionType": value["versionType"], "operation": operation}
            field = "versionChange"
        elif command in {"color.group.add", "color.group.delete", "color.group.rename"}:
            operation = command.rsplit(".", 1)[1]
            group_id = (
                _created_entity_ids(result, descriptor.action_id, prefix="group_")[0]
                if command in {"color.group.add", "color.group.rename"}
                else value.get("groupId")
            )
            body = {**mutation, "groupId": group_id, "name": value.get("newName", value.get("name", str(native_map.get("name") or ""))), "operation": operation}
            field = "groupChange"
        elif command in {"color.group.assign", "color.group.remove"}:
            operation = command.rsplit(".", 1)[1]
            body = {**mutation, "groupId": value.get("groupId"), "operation": operation}
            field = "membershipChange"
        elif command in {"color.node.lut_set", "color.node.label_set", "color.node.enable", "color.node.disable"}:
            body = {**mutation, "nodeIndex": value["nodeIndex"], "operation": command.rsplit(".", 1)[1]}
            field = "nodeChange"
        elif command == "color.node.reset":
            body, field = mutation, "graphReset"
        elif command in {"color.gallery.album.create", "color.gallery.album.rename", "color.gallery.album.switch"}:
            operation = command.rsplit(".", 1)[1]
            album_id = (
                _created_entity_ids(result, descriptor.action_id, prefix="album_")[0]
                if command in {"color.gallery.album.create", "color.gallery.album.rename"}
                else value.get("albumId")
            )
            body = {
                **mutation,
                "albumId": album_id,
                "name": value.get(
                    "newName",
                    value.get(
                        "name", str(native_map.get("name", native_map.get("album")) or "")
                    ),
                ),
                "operation": operation,
            }
            field = "albumChange"
        elif command in {"color.gallery.still.import", "color.gallery.still.delete"}:
            operation = command.rsplit(".", 1)[1]
            still_ids = [value["stillId"]] if "stillId" in value else _created_entity_ids(result, descriptor.action_id, prefix="still_")
            body = {**mutation, "albumId": value["albumId"], "stillIds": still_ids, "operation": operation}
            field = "stillChange"
        elif command == "color.gallery.still.grab":
            ids = _created_entity_ids(result, descriptor.action_id, prefix="still_")
            albums = _created_entity_ids(result, descriptor.action_id, prefix="album_")
            body = {**mutation, "albumId": albums[0], "stillId": ids[0]}
            field = "grabbedStill"
        elif command == "color.gallery.still.apply":
            body = {**mutation, "albumId": value["albumId"], "stillId": value["stillId"], "mode": value["mode"]}
            field = "appliedGrade"
        else:
            raise InventoryValidationError("Color exact result projector is incomplete")
    return {"actionId": descriptor.action_id, field: body}


def _normalized_state(
    descriptor: ColorActionDescriptor,
    value: Mapping[str, Any],
    native_result: Any,
    artifact_evidence: Any,
    prepared: Mapping[str, Any],
) -> dict[str, Any]:
    kind = color_result_kind(descriptor.command_id)
    selector_list = {
        "color.power_grade.list": ("still", "color_entity_"),
        "color.qualifier.list": ("qualifier", "color_entity_"),
        "color.tracker.list": ("tracker", "color_entity_"),
        "color.window.list": ("window", "color_entity_"),
    }.get(descriptor.command_id)
    entities = []
    if selector_list is not None:
        entity_kind, prefix = selector_list
        for fallback, row in enumerate(_native_rows(native_result), 1):
            label = _row_label(row)
            ordinal_value = row.get("index", row.get("order", row.get("position", fallback)))
            ordinal = ordinal_value if isinstance(ordinal_value, int) and not isinstance(ordinal_value, bool) and ordinal_value > 0 else fallback
            if label is None:
                raise InventoryValidationError("Color selector list result omitted its public label")
            entities.append({
                "id": _stable_selector_id(prepared, label, prefix=prefix, ordinal=ordinal),
                "kind": entity_kind,
                "name": label,
                "index": ordinal,
                "enabled": row.get("enabled") if isinstance(row.get("enabled"), bool) else None,
                "values": [],
            })
    artifacts = []
    for record in artifact_evidence if isinstance(artifact_evidence, list) else ():
        if not isinstance(record, Mapping):
            continue
        artifact_kind = _artifact_kind(descriptor, value)
        artifacts.append(
            {
                "artifactId": record["artifactId"],
                "kind": artifact_kind,
                "mediaType": _artifact_media_type(artifact_kind, value),
                "sha256": record["sha256"],
                "byteLength": record["byteLength"],
            }
        )
    return {
        "kind": kind,
        "entities": entities,
        "values": _safe_named_values(native_result),
        "artifacts": artifacts,
    }


def _normalized_color_projection(
    descriptor: ColorActionDescriptor,
    context: Mapping[str, Any],
    prepared: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    value = prepared["lowering"]["normalizedInput"]
    native = result.get("nativeResult")
    artifacts = result.get("artifactEvidence")
    target = _public_target(context, value)
    evidence = [
        {
            "kind": "artifact_readback" if artifacts else "structural_readback",
            "summary": (
                "Managed destination content was hashed after the authoritative handler returned."
                if artifacts
                else "Independent inspection confirmed the authoritative Color result."
            ),
            "artifactId": artifacts[0]["artifactId"] if isinstance(artifacts, list) and artifacts else None,
        }
    ]
    verification = {
        "outcome": "passed",
        "evidence": evidence,
        "protectedState": "preserved" if descriptor.operation_class == "mutation" else "not_applicable",
    }
    data = _normalized_state(descriptor, value, native, artifacts, prepared)
    if descriptor.operation_class == "read":
        payload: dict[str, Any] = {
            "status": "completed",
            "targets": [target],
            "data": data,
            "verification": verification,
        }
    elif descriptor.verification_profile == "artifact_hash_nonempty_and_context":
        if not isinstance(artifacts, list) or not artifacts:
            raise InventoryValidationError("Color artifact result lacks file evidence")
        payload = {
            "status": "completed",
            "changed": True,
            "targets": [target],
            "data": data,
            "verification": verification,
            "recovery": {
                "state": "not_needed",
                "retry": "inspect_state_first",
                "guidance": "The managed destination is complete and verified; inspect it before any retry.",
            },
        }
    else:
        revision = _revision_change(value, result)
        if not revision["changed"]:
            raise InventoryValidationError("Color mutation did not advance its bound revision")
        before_state = {
            "kind": color_result_kind(descriptor.command_id),
            "entities": [],
            "values": [],
            "artifacts": [],
        }
        payload = {
            "status": "completed",
            "changed": True,
            "revision": {
                "relationship": "advanced",
                "before": revision["revisionBefore"],
                "after": revision["revisionAfter"],
            },
            "targets": [target],
            "change": {
                "kind": color_result_kind(descriptor.command_id),
                "before": before_state,
                "after": data,
            },
            "verification": verification,
            "recovery": {
                "state": "not_needed",
                "retry": "inspect_state_first",
                "guidance": "The requested Color state and revision were independently read back.",
            },
        }
    return {"actionId": descriptor.action_id, "payload": payload}


@dataclass(frozen=True)
class ColorPreparedActionDescriptor:
    descriptor: ColorActionDescriptor
    runtime: ColorPreparedActionRuntime

    version = 1
    available = True

    @property
    def operation_class(self) -> str:
        return self.descriptor.operation_class

    @property
    def capability_id(self) -> str | None:
        return self.descriptor.capability_id

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise InventoryValidationError("Color action input must be an object")
        schema = _input_schema(self.descriptor.command_id)
        _validate_typed_value(value, schema, "input")
        return deepcopy(dict(value))

    @staticmethod
    def _runtime_context(context: Mapping[str, Any]) -> dict[str, Any]:
        """Open only the carrier-captured Color bindings for this invocation."""

        captured = context.get("privateBindings")
        private = (
            captured
            if isinstance(captured, Mapping) and captured
            else context
        )
        if not isinstance(private, Mapping):
            raise InventoryValidationError("Color carrier private bindings are unavailable")
        private_timeline = private.get("timeline")
        return build_production_color_runtime_context(
            context,
            mutation_base=(
                context.get("mutationBase")
                if isinstance(context.get("mutationBase"), Mapping)
                else None
            ),
            private_target_bindings=private.get("privateTargetBindings", {}),
            private_selector_bindings=private.get("privateSelectorBindings", {}),
            private_named_clip_bindings=private.get("privateNamedClipBindings", {}),
            private_all_timeline_item_ids=private.get("privateAllTimelineItemIds", []),
            private_managed_artifacts=private.get("privateManagedArtifacts", {}),
            private_mutation_guard=(
                private_timeline.get("mutationGuard")
                if isinstance(private_timeline, Mapping)
                else None
            ),
        )

    def _bind(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> tuple[PreparedColorAction, dict[str, Any]]:
        live = self.runtime.inspect(context, self.descriptor, value)
        bound = _prepare_bound_descriptor(
            self.descriptor,
            value,
            live,
            _kernel_digest,
            expected_revision=live["revision"],
        )
        return bound, live

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        context = self._runtime_context(context)
        bound, live = self._bind(context, value)
        artifact_custody = _artifact_custody(self.descriptor, value, context)
        project_id = context.get("project", {}).get("projectId")
        timeline_id = context.get("timeline", {}).get("timelineId")
        targets = [
            {**dict(target), "projectId": project_id, "timelineId": timeline_id}
            for target in bound.targets
        ]
        minimum = ["readback", "structural"]
        if (
            self.descriptor.verification_profile == "color_readback_revision_and_rendered_frame"
            or self.descriptor.action_id in {
                "cutagent.action.color.node.enable",
                "cutagent.action.color.node.disable",
            }
        ):
            minimum.append("rendered")
        if self.descriptor.verification_profile == "artifact_hash_nonempty_and_context":
            minimum.append("file")
        if self.operation_class == "read":
            read_minimum = ["readback"]
            if self.descriptor.verification_profile == "artifact_hash_nonempty_and_context":
                read_minimum.append("file")
            return {
                "targets": targets,
                "preState": deepcopy(dict(bound.private_pre_state)),
                "impact": {
                    "contractVersion": 1,
                    "status": "read",
                    "complete": True,
                    "targetDigests": [
                        _kernel_digest("targets", target) for target in targets
                    ],
                    "resultMaximumBytes": 65_536,
                },
                "lowering": {
                    "normalizedInput": deepcopy(dict(value)),
                    "privateTargetBinding": deepcopy(live.get("privateTargetBinding")),
                    "privateSelectorBindings": deepcopy(context.get("privateSelectorBindings", {})),
                    "privateManagedArtifacts": deepcopy(context.get("privateManagedArtifacts", {})),
                    "artifactCustody": deepcopy(artifact_custody),
                },
                "verification": {
                    "minimumEvidence": read_minimum,
                    "protectedState": self.descriptor.protected_state,
                },
                "recovery": {"strategy": "not_applicable"},
            }
        policy = context.get("mutationPolicy")
        if not isinstance(policy, Mapping):
            raise InventoryValidationError("Color action has no durable Mutation Policy scope")
        required_policy = ("registryDigest", "scopeId", "scopeRevision", "projectLibraryId")
        if any(not isinstance(policy.get(field_name), (str, int)) for field_name in required_policy):
            raise InventoryValidationError("Color Mutation Policy binding is incomplete")
        effect_targets = _color_policy_effect_targets(bound.targets)
        operation_kind = "delete" if self.descriptor.destructive else (
            "create" if any(token in self.descriptor.action_id for token in (".add", ".create", ".import", ".grab")) else "update"
        )
        impact = _merge_carrier_mutation_base(context, {
            "status": "mutation",
            "complete": True,
            "effects": [
                {
                    "operation": self.descriptor.action_id.removeprefix("cutagent.action."),
                    "kind": operation_kind,
                    "trackTypes": sorted(
                        {str(target["trackType"]) for target in effect_targets if target.get("trackType") in {"video", "audio"}}
                    ),
                    "targets": effect_targets,
                    "placementIntent": "explicit",
                    "broad": False,
                    "ambiguous": False,
                    "complete": True,
                }
            ],
            "closedComposition": True,
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
            "preState": deepcopy(dict(bound.private_pre_state)),
            "impact": impact,
            "lowering": {
                "normalizedInput": deepcopy(dict(value)),
                "mutationGuard": live.get("mutationGuard"),
                "privateTargetBinding": deepcopy(live.get("privateTargetBinding")),
                "privateSelectorBindings": deepcopy(context.get("privateSelectorBindings", {})),
                "privateManagedArtifacts": deepcopy(context.get("privateManagedArtifacts", {})),
                "artifactCustody": deepcopy(artifact_custody),
            },
            "verification": {"minimumEvidence": minimum, "protectedState": self.descriptor.protected_state},
            "recovery": {
                "strategy": (
                    "restore_previous_page"
                    if self.descriptor.action_id == "cutagent.action.page.switch"
                    else "authorized_execution_checkpoint_restore"
                )
            },
        }

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        context = self._runtime_context(context)
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise InventoryValidationError("Prepared Color input is unavailable")
        rebound, _live = self._bind(context, value)
        return {
            "targets": [
                {
                    **dict(target),
                    "projectId": context.get("project", {}).get("projectId"),
                    "timelineId": context.get("timeline", {}).get("timelineId"),
                }
                for target in rebound.targets
            ],
            "preState": deepcopy(dict(rebound.private_pre_state)),
        }

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Mapping[str, Any]:
        context = self._runtime_context(context)
        return self.runtime.execute(context, self.descriptor, prepared)

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        context = self._runtime_context(context)
        value = prepared["lowering"]["normalizedInput"]
        verification_context = dict(context)
        verification_context["privateColorInspectionPhase"] = "verification"
        after = self.runtime.inspect(verification_context, self.descriptor, value)
        before = prepared["preState"]
        after_state = after["preState"]
        if isinstance(result, dict) and self.operation_class == "mutation":
            result["privatePostEntityIds"] = _post_entity_ids(
                context, self.descriptor, value, before, after
            )
        native_result = result.get("nativeResult") if isinstance(result, Mapping) else None
        artifact_evidence = result.get("artifactEvidence") if isinstance(result, Mapping) else None
        unchanged = _canonical_digest(before) == _canonical_digest(after_state)
        exact_effect = (
            native_result is not None and unchanged
            if self.operation_class == "read"
            else _requested_effect_matches(
                self.descriptor, value, native_result, before, after_state,
                prepared, artifact_evidence,
            )
        )
        protected_before = {key: before.get(key) for key in ("identity", "timeline")}
        protected_after = {key: after_state.get(key) for key in ("identity", "timeline")}
        protected_preserved = _canonical_digest(protected_before) == _canonical_digest(protected_after)
        required = set(prepared["verification"]["minimumEvidence"])
        evidence = [
            {
                "modality": "readback",
                "digest": _kernel_digest("pre-state", after_state),
                "summary": "The exact bound Color target was independently inspected after execution.",
            }
        ]
        if self.operation_class == "mutation":
            evidence.append(
                {
                    "modality": "structural",
                    "digest": _kernel_digest(
                        "pre-state",
                        {"before": protected_before, "after": protected_after},
                    ),
                    "summary": "Protected project and timeline identity remained unchanged.",
                }
            )
        if "file" in required and isinstance(artifact_evidence, list) and artifact_evidence:
            evidence.append(
                {
                    "modality": "file",
                    "digest": _kernel_digest("execution", artifact_evidence),
                    "summary": "Every managed destination exists, is non-empty, and has a computed SHA-256 digest.",
                }
            )
        rendered = _rendered_frame_proof(native_result)
        if rendered is not None:
            evidence.append(
                {
                    "modality": "rendered",
                    "digest": str(rendered["evidenceDigest"]),
                    "summary": "The handler supplied a verified rendered-frame comparison and digest.",
                }
            )
        modalities = {item["modality"] for item in evidence}
        structural_transition = (
            self.descriptor.verification_profile == "structural_readback_and_revision"
            and _canonical_digest({
                "selectedColor": before.get("selectedColor"),
                "semanticReadback": before.get("semanticReadback"),
            })
            != _canonical_digest({
                "selectedColor": after_state.get("selectedColor"),
                "semanticReadback": after_state.get("semanticReadback"),
            })
        )
        revision_changed = (
            self.operation_class == "read"
            or self.descriptor.action_id == "cutagent.action.page.switch"
            or structural_transition
            or rendered is not None
            or (
                self.descriptor.verification_profile == "artifact_hash_nonempty_and_context"
                and isinstance(artifact_evidence, list)
                and bool(artifact_evidence)
            )
            or isinstance(prepared.get("lowering", {}).get("mutationGuard"), str)
            and isinstance(after.get("mutationGuard"), str)
            and prepared["lowering"]["mutationGuard"] != after["mutationGuard"]
        )
        passed = (
            exact_effect
            and protected_preserved
            and required <= modalities
            and revision_changed
        )
        if isinstance(result, dict) and isinstance(after.get("revision"), str):
            result["verifiedAfterRevision"] = after["revision"]
        return {"outcome": "passed" if passed else "failed", "evidence": evidence, "protectedStatePreserved": protected_preserved}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        context = self._runtime_context(context)
        custody = prepared.get("lowering", {}).get("artifactCustody", {})
        has_destination = isinstance(custody, Mapping) and any(
            isinstance(record, Mapping) and record.get("role") == "destination"
            for record in custody.values()
        )
        if self.operation_class == "read" and not has_destination:
            return {"outcome": "not_applicable", "attempted": False, "manualActionRequired": False}
        return self.runtime.recover(context, self.descriptor, prepared)

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        if not isinstance(result, Mapping):
            raise InventoryValidationError("Color handler returned invalid result custody")
        if self.descriptor.command_id == "page.switch":
            native = result.get("nativeResult")
            native = native if isinstance(native, Mapping) else {}
            projection = {
                "actionId": self.descriptor.action_id,
                "navigation": {
                    "previousPage": prepared.get("preState", {}).get("page"),
                    "currentPage": native.get("current_page", native.get("currentPage")),
                    "changed": bool(native.get("changed")),
                },
            }
        elif color_action_result_schema(
            self.descriptor.action_id, self.descriptor.command_id
        ) is not None:
            projection = _exact_color_projection(
                self.descriptor, context, prepared, result
            )
        else:
            projection = _normalized_color_projection(
                self.descriptor, context, prepared, result
            )
        _reject_private_keys(projection)
        return self._validated_public_result(projection)

    def _validated_public_result(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise InventoryValidationError("Color public result must be an object")
        result = deepcopy(dict(value))
        schema = (
            reviewed_page_result_schema(self.descriptor.action_id, self.descriptor.command_id)
            if self.descriptor.command_id == "page.switch"
            else color_action_result_schema(
                self.descriptor.action_id, self.descriptor.command_id
            )
        )
        if schema is not None:
            validate_color_public_result(result, schema)
        else:
            normalized = normalized_color_action_result_schema(
                self.descriptor.action_id, self.descriptor.command_id
            )
            if normalized is None or set(result) != {"actionId", "payload"}:
                raise InventoryValidationError("Color normalized result owner is missing")
            if result.get("actionId") != self.descriptor.action_id or not isinstance(
                result.get("payload"), Mapping
            ):
                raise InventoryValidationError("Color normalized result is invalid")
            validate_color_public_result(result, normalized)
        _reject_private_keys(result)
        return result

    def validate_public_result(self, value: Any) -> bool:
        self._validated_public_result(value)
        return True


@dataclass(frozen=True)
class UnavailableColorPreparedActionDescriptor:
    """Complete fail-closed Packet 0 lifecycle for an unreviewed Color action."""

    descriptor: ColorActionDescriptor

    version = 1
    available = False

    @property
    def operation_class(self) -> str:
        return self.descriptor.operation_class

    @property
    def capability_id(self) -> str | None:
        return self.descriptor.capability_id

    def _unavailable(self) -> None:
        raise InventoryValidationError("Color action is unavailable in the signed runtime")

    def validate_input(self, value: Any) -> Any:
        self._unavailable()

    def prepare(self, context: Mapping[str, Any], value: Any) -> Mapping[str, Any]:
        self._unavailable()

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Mapping[str, Any]:
        self._unavailable()

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        self._unavailable()

    def verify(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any
    ) -> Mapping[str, Any]:
        self._unavailable()

    def recover(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        failure: BaseException,
    ) -> Mapping[str, Any]:
        self._unavailable()

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        self._unavailable()

    def validate_public_result(self, value: Any) -> Any:
        self._unavailable()


def color_prepared_action_descriptors(
    runtime: ColorPreparedActionRuntime | None = None,
) -> Mapping[str, Any]:
    """Return complete lifecycle objects for every owned Color action."""

    concrete = runtime or ColorPreparedActionRuntime()
    return MappingProxyType(
        {
            action_id: (
                ColorPreparedActionDescriptor(descriptor, concrete)
                if action_id in CALLABLE_COLOR_ACTION_IDS
                else UnavailableColorPreparedActionDescriptor(descriptor)
            )
            for action_id, descriptor in COLOR_ACTION_DESCRIPTORS.items()
        }
    )


def color_prepared_action_contribution(
    runtime: ColorPreparedActionRuntime | None = None,
) -> Mapping[str, Any]:
    descriptors = color_prepared_action_descriptors(runtime)
    return MappingProxyType({
        action_id: descriptor if getattr(descriptor, "available", False) else object()
        for action_id, descriptor in descriptors.items()
    })


def build_production_color_prepared_action_contributions(
) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    """Instantiate the real Color contribution for the shared signed host."""

    return ((COLOR_PREPARED_ACTION_CONTRIBUTION_NAME, color_prepared_action_contribution()),)


def register_color_prepared_actions(registry: Any, runtime: ColorPreparedActionRuntime | None = None) -> None:
    registry.register_contribution(
        COLOR_PREPARED_ACTION_CONTRIBUTION_NAME,
        color_prepared_action_contribution(runtime),
    )
