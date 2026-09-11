"""Private Timeline/Version mutation descriptors and fail-closed admission.

This packet deliberately owns no transport, receipt signing, authorization, or
execution lifecycle. Packet 0 consumes the prepared descriptor inside the
signed proprietary runtime. The bridge receives only an opaque receipt and the
public-safe impact projection returned by ``prepare_timeline_version_action``.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Mapping, Sequence


DescriptorFamily = Literal["stable", "multi_target", "version"]
BindingLevel = Literal["project", "project+timeline", "workflow"]
TargetCardinality = Literal["one_per_kind", "one_or_more"]


class DescriptorAdmissionError(ValueError):
    """A mutation descriptor could not prove a closed pre-authorization impact."""

    code = "VALIDATION_ERROR"


@dataclass(frozen=True)
class TimelineVersionMutationDescriptor:
    action_id: str
    command_id: str
    family: DescriptorFamily
    binding_level: BindingLevel
    effect_kind: Literal["create", "update", "delete", "artifact"]
    target_kinds: tuple[str, ...]
    target_cardinality: TargetCardinality
    explicit_id_fields: tuple[str, ...] = ()
    exact_track: bool = False
    fixed_track_type: Literal["video", "audio", "subtitle"] | None = None
    closed_composition: bool = False
    linked_topology: bool = False
    artifact_destination: bool = False
    operation_variant: str | None = None
    checkpoint_policy: Literal[
        "checkpoint_restore", "durable_workflow", "checkpoint_history"
    ] = "checkpoint_restore"
    protected_state: tuple[str, ...] = (
        "project_identity",
        "timeline_identity",
        "unaffected_tracks",
        "unaffected_items",
        "linked_topology",
        "active_context",
    )
    minimum_evidence: tuple[str, ...] = (
        "revision_readback",
        "structural_readback",
        "protected_state_readback",
    )
    recovery: str = "restore_checkpoint_and_verify_context"


def _stable(
    command_id: str,
    *,
    binding: BindingLevel = "project+timeline",
    effect: Literal["create", "update", "delete", "artifact"] = "update",
    target_kinds: tuple[str, ...] = ("timeline",),
    ids: tuple[str, ...] = (),
    track: bool = False,
    fixed_track_type: Literal["video", "audio", "subtitle"] | None = None,
    linked: bool = False,
    artifact: bool = False,
    operation_variant: str | None = None,
) -> TimelineVersionMutationDescriptor:
    protected = (
        "project_identity",
        "timeline_identity",
        "unaffected_tracks",
        "unaffected_items",
        "linked_topology",
        "active_context",
    )
    evidence = ("revision_readback", "structural_readback", "protected_state_readback")
    recovery = "restore_checkpoint_and_verify_context"
    if artifact:
        protected += ("filesystem_destination",)
        evidence = ("artifact_readback", "context_readback", "protected_state_readback")
        recovery = "restore_checkpoint_context_and_artifact_destination"
    return TimelineVersionMutationDescriptor(
        action_id=f"cutagent.action.{command_id}",
        command_id=command_id,
        family="stable",
        binding_level=binding,
        effect_kind="artifact" if artifact else effect,
        target_kinds=target_kinds,
        target_cardinality="one_per_kind",
        explicit_id_fields=ids,
        exact_track=track,
        fixed_track_type=fixed_track_type,
        linked_topology=linked,
        artifact_destination=artifact,
        operation_variant=operation_variant,
        protected_state=protected,
        minimum_evidence=evidence,
        recovery=recovery,
    )


def _multi(
    command_id: str,
    *,
    target_kinds: tuple[str, ...],
    ids: tuple[str, ...] = (),
    track: bool = False,
    linked: bool = True,
    effect: Literal["create", "update", "delete"] | None = None,
) -> TimelineVersionMutationDescriptor:
    return TimelineVersionMutationDescriptor(
        action_id=f"cutagent.action.{command_id}",
        command_id=command_id,
        family="multi_target",
        binding_level="project+timeline",
        effect_kind=effect
        or ("delete" if command_id == "timeline.items.delete" else "update"),
        target_kinds=target_kinds,
        target_cardinality="one_or_more",
        explicit_id_fields=ids,
        exact_track=track,
        closed_composition=True,
        linked_topology=linked,
        protected_state=(
            "project_identity",
            "timeline_identity",
            "unaffected_tracks",
            "unaffected_items",
            "linked_topology",
            "active_context",
        ),
        minimum_evidence=(
            "revision_readback",
            "closed_target_readback",
            "protected_state_readback",
        ),
        recovery="restore_checkpoint_and_verify_closed_composition",
    )


def _version(
    command_id: str, effect: Literal["create", "update", "delete"]
) -> TimelineVersionMutationDescriptor:
    return TimelineVersionMutationDescriptor(
        action_id=f"cutagent.action.{command_id}",
        command_id=command_id,
        family="version",
        binding_level="workflow",
        effect_kind=effect,
        target_kinds=("project", "timeline"),
        target_cardinality="one_per_kind",
        explicit_id_fields=(),
        closed_composition=command_id == "version.prune",
        checkpoint_policy=(
            "durable_workflow"
            if command_id in {"version.create", "version.restore"}
            else "checkpoint_history"
        ),
        protected_state=(
            "checkpoint_history",
            "project_identity",
            "timeline_identity",
            "active_context",
        ),
        minimum_evidence=(
            "checkpoint_readback",
            "context_readback",
            "protected_state_readback",
        ),
        recovery="inspect_checkpoint_history_and_restore_bound_context",
    )


_DESCRIPTORS = (
    # 35 exact, stable Timeline mutations. Existing semantic marker, caption,
    # move, blade, retime and keyframe owners are intentionally absent.
    _stable(
        "timeline.create", binding="project", effect="create", target_kinds=("project",)
    ),
    _stable(
        "timeline.delete",
        binding="project",
        effect="delete",
        target_kinds=("timeline",),
        ids=("timelineId",),
    ),
    _stable(
        "timeline.duplicate",
        binding="project",
        effect="create",
        target_kinds=("timeline",),
        ids=("sourceTimelineId",),
    ),
    _stable("timeline.export", effect="artifact", ids=("timelineId",), artifact=True),
    _stable(
        "timeline.inspect_export", effect="artifact", ids=("timelineId",), artifact=True
    ),
    _stable("timeline.fairlight_preset.apply"),
    _stable(
        "timeline.frame_export", effect="artifact", ids=("timelineId",), artifact=True
    ),
    _stable(
        "timeline.fusion_composition.insert",
        effect="create",
        target_kinds=("timeline", "track"),
        track=True,
        fixed_track_type="video",
    ),
    _stable("timeline.grab_still", effect="artifact", artifact=True),
    _stable(
        "timeline.import", binding="project", effect="create", target_kinds=("project",)
    ),
    _stable("timeline.import_into", effect="create", linked=True),
    _stable(
        "timeline.insert_generator",
        effect="create",
        target_kinds=("timeline", "track"),
        track=True,
        fixed_track_type="video",
    ),
    _stable(
        "timeline.insert_title",
        effect="create",
        target_kinds=("timeline", "track"),
        track=True,
        fixed_track_type="video",
    ),
    _stable(
        "timeline.layer.ensure_media",
        effect="create",
        target_kinds=("media", "track"),
        ids=("mediaPoolItemId",),
        track=True,
        fixed_track_type="video",
        linked=True,
    ),
    _stable("timeline.mark.clear"),
    _stable("timeline.mark.set"),
    _stable("timeline.playhead.set"),
    _stable(
        "timeline.preview_export", effect="artifact", ids=("timelineId",), artifact=True
    ),
    _stable("timeline.rename", binding="project", ids=("timelineId",)),
    _stable("timeline.set_start_tc"),
    _stable("timeline.settings_set"),
    _stable("timeline.output_blanking.set"),
    _stable("timeline.start_tc", operation_variant="get_or_set"),
    _stable("timeline.stereo_convert", linked=True),
    _stable("timeline.still.grab_all", effect="artifact", artifact=True, linked=True),
    _stable("timeline.switch", binding="project", ids=("timelineId",)),
    _stable(
        "timeline.thumbnail", effect="artifact", ids=("timelineId",), artifact=True
    ),
    _stable(
        "timeline.track.add", effect="create", target_kinds=("timeline",), track=True
    ),
    _stable(
        "timeline.track.delete",
        effect="delete",
        target_kinds=("track",),
        track=True,
        linked=True,
    ),
    _stable("timeline.track.disable", target_kinds=("track",), track=True),
    _stable("timeline.track.enable", target_kinds=("track",), track=True),
    _stable("timeline.track.lock", target_kinds=("track",), track=True),
    _stable("timeline.track.rename", target_kinds=("track",), track=True),
    _stable("timeline.track.unlock", target_kinds=("track",), track=True),
    _stable(
        "timeline.voice_isolation.set",
        target_kinds=("track",),
        track=True,
        fixed_track_type="audio",
    ),
    # Seven actions whose impact may span multiple objects. Preparation accepts
    # them only after private live resolution has closed the full target set.
    _multi(
        "timeline.clip_color.batch",
        target_kinds=("clip",),
        linked=False,
    ),
    _multi("timeline.compound_create", target_kinds=("clip",), track=True, linked=True),
    _multi(
        "timeline.dolby.analyze",
        target_kinds=("clip",),
        ids=("timelineItemIds",),
        linked=False,
    ),
    _multi(
        "timeline.fusion_clip.create",
        target_kinds=("clip",),
        ids=("timelineItemIds",),
        linked=True,
    ),
    _multi("timeline.items.delete", target_kinds=("clip",), track=True, linked=True),
    _multi(
        "timeline.items.set_duration",
        target_kinds=("clip",),
        ids=("timelineItemId",),
        track=True,
        linked=True,
    ),
    _multi(
        "timeline.sync_clips",
        target_kinds=("media", "timeline"),
        ids=("sourceItemIds",),
        linked=True,
        effect="create",
    ),
    # Version mutations remain under the durable workflow/checkpoint authority.
    _version("version.create", "create"),
    _version("version.prune", "delete"),
    _version("version.restore", "update"),
)

TIMELINE_VERSION_MUTATION_DESCRIPTORS: Mapping[
    str, TimelineVersionMutationDescriptor
] = MappingProxyType({descriptor.action_id: descriptor for descriptor in _DESCRIPTORS})

if len(TIMELINE_VERSION_MUTATION_DESCRIPTORS) != len(_DESCRIPTORS):
    raise RuntimeError(
        "Timeline/Version mutation descriptor action IDs must be unique."
    )
if sum(row.family == "stable" for row in _DESCRIPTORS) != 35:
    raise RuntimeError(
        "Timeline/Version descriptor packet must contain 35 stable Timeline actions."
    )
if sum(row.family == "multi_target" for row in _DESCRIPTORS) != 7:
    raise RuntimeError(
        "Timeline/Version descriptor packet must contain seven multi-target Timeline actions."
    )
if sum(row.family == "version" for row in _DESCRIPTORS) != 3:
    raise RuntimeError(
        "Timeline/Version descriptor packet must contain three Version actions."
    )


def _fail(message: str) -> None:
    raise DescriptorAdmissionError(message)


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _identity(authority: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = authority.get(key)
    if (
        not isinstance(value, Mapping)
        or not _non_empty_text(value.get("id"))
        or not _non_empty_text(value.get("revision"))
    ):
        _fail(
            f"Exact live {key} identity and revision are required before authorization."
        )
    return value


def _flatten_ids(
    input_value: Mapping[str, Any], fields: Sequence[str]
) -> tuple[str, ...]:
    values: list[str] = []
    for field in fields:
        value = input_value.get(field)
        if (
            value is None
            and field == "timelineItemId"
            and isinstance(input_value.get("updates"), list)
        ):
            value = [
                update.get(field)
                for update in input_value["updates"]
                if isinstance(update, Mapping)
            ]
        if value is None:
            continue
        candidates = value if isinstance(value, list) else [value]
        if not candidates or any(
            not _non_empty_text(candidate) for candidate in candidates
        ):
            _fail(f"{field} must contain exact non-empty object identities.")
        values.extend(str(candidate) for candidate in candidates)
    return tuple(values)


def _exact_targets(
    descriptor: TimelineVersionMutationDescriptor,
    input_value: Mapping[str, Any],
    authority: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    raw = authority.get("resolvedTargets")
    if not isinstance(raw, list) or not raw:
        _fail(
            "Complete private live target resolution is required before authorization."
        )
    targets: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for target in raw:
        if not isinstance(target, Mapping):
            _fail("Resolved mutation targets must be stable identity records.")
        kind = target.get("kind")
        stable_id = target.get("stableId")
        revision = target.get("revision")
        if (
            kind not in descriptor.target_kinds
            or not _non_empty_text(stable_id)
            or not _non_empty_text(revision)
        ):
            _fail(
                "Resolved mutation targets are incomplete or outside the descriptor impact."
            )
        if descriptor.command_id == "timeline.dolby.analyze":
            native_id = target.get("nativeId")
            name = target.get("name")
            track_type = target.get("trackType")
            track_index = target.get("trackIndex")
            start = target.get("start")
            end = target.get("end")
            if (
                not _non_empty_text(native_id)
                or native_id != native_id.strip()
                or len(native_id) > 4096
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in native_id
                )
                or not isinstance(name, str)
                or track_type not in {"video", "audio", "subtitle"}
                or not isinstance(track_index, int)
                or isinstance(track_index, bool)
                or track_index < 1
                or not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or end <= start
            ):
                _fail(
                    "Dolby analysis requires exact private native target descriptors."
                )
        identity = (str(kind), str(stable_id))
        if identity in seen:
            _fail("Resolved mutation targets contain duplicate identities.")
        seen.add(identity)
        targets.append(
            MappingProxyType(
                {
                    key: target[key]
                    for key in (
                        "kind",
                        "stableId",
                        "publicId",
                        "revision",
                        "trackType",
                        "trackIndex",
                        "mediaRole",
                        "impactRole",
                        *(
                            ("nativeId", "name", "start", "end")
                            if descriptor.command_id == "timeline.dolby.analyze"
                            else ()
                        ),
                    )
                    if key in target
                }
            )
        )

    if descriptor.target_cardinality == "one_per_kind" and len(targets) != len(
        descriptor.target_kinds
    ):
        # A descriptor with two distinct target kinds needs exactly one of each.
        if not (len(descriptor.target_kinds) == 1 and len(targets) == 1):
            _fail(
                "The mutation descriptor requires one exact target of every declared kind."
            )
    for kind in descriptor.target_kinds:
        if not any(target.get("kind") == kind for target in targets):
            _fail(f"The mutation descriptor is missing its exact {kind} target.")

    requested_ids = _flatten_ids(input_value, descriptor.explicit_id_fields)
    if len(set(requested_ids)) != len(requested_ids):
        _fail("Requested mutation identities must be unique.")
    if (
        descriptor.family == "multi_target"
        and descriptor.explicit_id_fields
        and not requested_ids
    ):
        _fail("A multi-target mutation cannot default to all live objects.")
    for requested_id in requested_ids:
        matches = [
            target for target in targets if target.get("publicId") == requested_id
        ]
        if len(matches) != 1:
            _fail(
                "Every requested identity must resolve to exactly one live stable target."
            )
    if requested_ids:
        resolved_requested = {
            str(target.get("publicId"))
            for target in targets
            if target.get("publicId") in set(requested_ids)
        }
        if resolved_requested != set(requested_ids):
            _fail("Resolved impact contains an undeclared or missing requested target.")
        requested_kind = descriptor.target_kinds[0]
        resolved_kind_ids = {
            str(target.get("publicId"))
            for target in targets
            if target.get("kind") == requested_kind
            and target.get("publicId") is not None
        }
        linked_duration_closure = (
            descriptor.command_id == "timeline.items.set_duration"
            and set(requested_ids).issubset(resolved_kind_ids)
            and all(
                target.get("impactRole")
                == ("requested" if target.get("publicId") in set(requested_ids) else "linked")
                for target in targets
                if target.get("kind") == requested_kind
            )
        )
        if descriptor.family == "multi_target" and resolved_kind_ids != set(requested_ids) and not linked_duration_closure:
            _fail(
                "Multi-target resolved impact is not the exact requested identity set."
            )

    if descriptor.exact_track:
        track_targets = [target for target in targets if target.get("kind") == "track"]
        clip_targets = [target for target in targets if target.get("kind") == "clip"]
        if (
            descriptor.target_kinds == ("timeline",)
            and descriptor.effect_kind == "create"
        ):
            # track.add creates a child track, so the exact destination coordinate
            # is part of the prepared placement rather than a pre-existing target.
            if not _non_empty_text(input_value.get("trackType")):
                _fail("Track creation requires an exact track type placement.")
        elif not track_targets and descriptor.target_kinds != ("clip",):
            _fail("An exact live track target is required before authorization.")
        for target in clip_targets:
            if target.get("trackType") not in {
                "video",
                "audio",
                "subtitle",
            } or not isinstance(target.get("trackIndex"), int):
                _fail(
                    "An exact live track coordinate is required for every resolved item."
                )
            expected_type = descriptor.fixed_track_type or input_value.get("trackType")
            expected_index = input_value.get("index", input_value.get("trackIndex"))
            if expected_type is not None and target.get("trackType") != expected_type:
                _fail("Resolved item track type differs from the requested track.")
            if (
                expected_index is not None
                and target.get("trackIndex") != expected_index
            ):
                _fail("Resolved item track index differs from the requested track.")
        for target in track_targets:
            expected_type = descriptor.fixed_track_type or input_value.get("trackType")
            expected_index = input_value.get("index", input_value.get("trackIndex"))
            if expected_type is not None and target.get("trackType") != expected_type:
                _fail("Resolved track type differs from the requested track.")
            if (
                expected_index is not None
                and target.get("trackIndex") != expected_index
            ):
                _fail("Resolved track index differs from the requested track.")
    return tuple(targets)


def _validate_action_specific_targeting(
    descriptor: TimelineVersionMutationDescriptor, input_value: Mapping[str, Any]
) -> None:
    command_id = descriptor.command_id
    if command_id == "timeline.compound_create":
        if (
            input_value.get("trackType") == "all"
            or input_value.get("trackIndex") is None
        ):
            _fail(
                "Compound creation requires one exact track, never an all-track selector."
            )
        if not isinstance(input_value.get("range"), Mapping):
            _fail("Compound creation requires an exact record range.")
    elif command_id == "timeline.items.delete":
        if input_value.get("trackType") not in {"video", "audio", "subtitle"}:
            _fail("Timeline item deletion cannot use an all-track selector.")
        if input_value.get("trackIndex") is None:
            _fail("Timeline item deletion requires one exact track index.")
        if input_value.get("recordRange") is None and not _non_empty_text(
            input_value.get("namePattern")
        ):
            _fail("Timeline item deletion requires an exact range or name selector.")
    elif command_id in {"timeline.dolby.analyze", "timeline.fusion_clip.create"}:
        if (
            command_id == "timeline.dolby.analyze"
            and input_value.get("enableProjectControls") is not False
        ):
            _fail(
                "SDK Dolby analysis requires project-control mutation to be disabled."
            )
        item_ids = input_value.get("timelineItemIds")
        if not isinstance(item_ids, list) or not item_ids:
            _fail("The multi-item action requires explicit Timeline item identities.")
    elif command_id == "timeline.sync_clips":
        if input_value.get("createTimeline") is True:
            _fail("SDK Timeline synchronization cannot create an undeclared Timeline.")
        source_ids = input_value.get("sourceItemIds")
        if not isinstance(source_ids, list) or not source_ids:
            _fail("Timeline synchronization requires explicit Media Pool identities.")
    elif command_id == "timeline.items.set_duration":
        updates = input_value.get("updates")
        if updates is not None:
            if (
                not isinstance(updates, list)
                or not updates
                or any(not isinstance(update, Mapping) for update in updates)
            ):
                _fail("Duration mutation updates must be a non-empty list of objects.")
            item_ids = [update.get("timelineItemId") for update in updates]
            if any(not _non_empty_text(item_id) for item_id in item_ids):
                _fail("Every duration mutation update requires an exact item identity.")
            if len(set(item_ids)) != len(item_ids):
                _fail("Duration mutation update identities must be unique.")
            if any(
                (update.get("duration") is None) == (update.get("targetEnd") is None)
                for update in updates
            ):
                _fail("Every duration mutation update requires exactly one duration or target end.")
        elif input_value.get("duration") is None and input_value.get("targetEnd") is None:
            _fail("Duration mutation requires a duration or exact target end.")
        elif input_value.get("timelineItemId") is None:
            if (
                input_value.get("trackType") not in {"video", "audio", "subtitle"}
                or input_value.get("trackIndex") is None
                or input_value.get("recordPosition") is None
            ):
                _fail(
                    "Duration mutation without an item ID requires an exact track and record position."
                )


_ORDINARY_NATIVE_PROJECT_COMMAND_IDS = frozenset(
    {
        "timeline.create",
        "timeline.delete",
        "timeline.dolby.analyze",
        "timeline.duplicate",
        "timeline.fairlight_preset.apply",
        "timeline.import",
        "timeline.mark.clear",
        "timeline.mark.set",
        "timeline.playhead.set",
        "timeline.rename",
        "timeline.set_start_tc",
        "timeline.settings_set",
        "timeline.output_blanking.set",
        "timeline.start_tc",
        "timeline.switch",
    }
)


def _private_pre_state(
    descriptor: TimelineVersionMutationDescriptor,
    project: Mapping[str, Any],
    timeline: Mapping[str, Any] | None,
    targets: Sequence[Mapping[str, Any]],
    authority: Mapping[str, Any],
) -> Mapping[str, Any]:
    pre_state = authority.get("privatePreState")
    if not isinstance(pre_state, Mapping):
        _fail(
            "A private canonical pre-state snapshot is required before authorization."
        )
    expected_target_ids = sorted(str(target["stableId"]) for target in targets)
    if pre_state.get("targetStableIds") != expected_target_ids:
        _fail("The private pre-state is not bound to the exact resolved targets.")
    digest = pre_state.get("protectedStateDigest")
    if not _sha256_digest(digest):
        _fail("The private pre-state lacks a canonical protected-state digest.")
    active_context = pre_state.get("activeContext")
    if (
        not isinstance(active_context, Mapping)
        or active_context.get("projectId") != project["id"]
    ):
        _fail("The private pre-state is not bound to the exact active project context.")
    if timeline is not None and active_context.get("timelineId") != timeline["id"]:
        _fail(
            "The private pre-state is not bound to the exact active timeline context."
        )
    native_project_id = pre_state.get("nativeProjectId")
    if (
        descriptor.command_id in _ORDINARY_NATIVE_PROJECT_COMMAND_IDS
        and (
            not _non_empty_text(native_project_id)
            or native_project_id != native_project_id.strip()
            or len(native_project_id) > 4096
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in native_project_id
            )
        )
    ):
        _fail("Ordinary Timeline execution requires an exact native project identity.")
    if descriptor.linked_topology and not _non_empty_text(
        pre_state.get("linkedTopologyDigest")
    ):
        _fail("Linked mutation pre-state requires the reciprocal topology digest.")
    if descriptor.command_id == "version.restore" and pre_state.get(
        "checkpointBindingDigest"
    ) != authority.get("checkpointBindingDigest"):
        _fail("Version restore pre-state does not bind the checkpoint contents.")
    if "parentCheckpointBindingDigest" in authority and pre_state.get(
        "parentCheckpointBindingDigest"
    ) != authority.get("parentCheckpointBindingDigest"):
        _fail("Version create pre-state does not bind the parent checkpoint contents.")
    return MappingProxyType(
        {
            "targetStableIds": tuple(expected_target_ids),
            "protectedStateDigest": digest,
            **(
                {"nativeProjectId": native_project_id}
                if descriptor.command_id in _ORDINARY_NATIVE_PROJECT_COMMAND_IDS
                else {}
            ),
            "activeContext": MappingProxyType(
                {
                    "projectId": project["id"],
                    **({"timelineId": timeline["id"]} if timeline is not None else {}),
                }
            ),
            **(
                {"linkedTopologyDigest": pre_state["linkedTopologyDigest"]}
                if descriptor.linked_topology
                else {}
            ),
            **(
                {
                    "resolvedCheckpointIds": tuple(
                        sorted(
                            str(value) for value in authority["resolvedCheckpointIds"]
                        )
                    )
                }
                if descriptor.command_id == "version.prune"
                else {}
            ),
            **(
                {"expectedCurrentStateHash": authority["expectedCurrentStateHash"]}
                if descriptor.command_id == "version.restore"
                else {}
            ),
            **(
                {"checkpointBindingDigest": authority["checkpointBindingDigest"]}
                if descriptor.command_id == "version.restore"
                else {}
            ),
            **(
                {
                    "parentCheckpointBindingDigest": authority[
                        "parentCheckpointBindingDigest"
                    ]
                }
                if descriptor.command_id == "version.create"
                and "parentCheckpointBindingDigest" in authority
                else {}
            ),
            **(
                {
                    "syncPlanDigest": authority["syncPlanDigest"],
                    "affectedTrackTypes": tuple(
                        sorted(authority["affectedTrackTypes"])
                    ),
                    "privateExecutionProfile": "sdk_timeline_sync_exact_v1",
                }
                if descriptor.command_id == "timeline.sync_clips"
                else {}
            ),
        }
    )


def prepare_timeline_version_action(
    action_id: str,
    input_value: Mapping[str, Any],
    authority: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Prepare a closed impact for Packet 0 before authorization is possible."""

    descriptor = TIMELINE_VERSION_MUTATION_DESCRIPTORS.get(action_id)
    if descriptor is None:
        _fail("The action is not owned by the Timeline/Version descriptor packet.")
    if not isinstance(input_value, Mapping) or not isinstance(authority, Mapping):
        _fail("Descriptor preparation requires typed input and private live authority.")
    if authority.get("stale") is not False:
        _fail("A stale or unconfirmed live snapshot cannot authorize mutation.")
    if authority.get("ambiguous") is not False or authority.get("complete") is not True:
        _fail("Ambiguous or incomplete mutation impact must fail before authorization.")
    if authority.get("broad") is True:
        _fail("Broad mutation impact must be resolved to a closed exact target set.")
    _validate_action_specific_targeting(descriptor, input_value)

    project = _identity(authority, "project")
    if (
        input_value.get("projectId") is not None
        and input_value.get("projectId") != project["id"]
    ):
        _fail("The requested project identity differs from the live project authority.")
    if descriptor.binding_level == "project":
        requested_project_revision = input_value.get("revision")
        if (
            requested_project_revision is None
            or requested_project_revision != project["revision"]
        ):
            _fail("The requested project revision is missing or stale.")
    timeline: Mapping[str, Any] | None = None
    if descriptor.binding_level == "project+timeline" or descriptor.family == "version":
        timeline = _identity(authority, "timeline")
        if (
            input_value.get("timelineId") is not None
            and input_value.get("timelineId") != timeline["id"]
        ):
            _fail(
                "The requested timeline identity differs from the live timeline authority."
            )
        requested_revision = input_value.get(
            "revision", input_value.get("expectedRevision")
        )
        if (
            requested_revision is not None
            and requested_revision != timeline["revision"]
        ):
            _fail("The requested timeline revision is stale.")
        if descriptor.family == "stable" and requested_revision is None:
            if descriptor.operation_variant not in {"set", "get_or_set"}:
                _fail("A live timeline mutation requires an explicit current revision.")

    if descriptor.operation_variant in {"set", "get_or_set"}:
        operation = input_value.get("operation")
        if not isinstance(operation, Mapping) or operation.get("kind") not in (
            {"set"} if descriptor.operation_variant == "set" else {"get", "set"}
        ):
            _fail(
                "The Timeline start-time descriptor received an unsupported operation variant."
            )
        if operation.get("kind") == "set" and operation.get("revision") != timeline["revision"]:
            _fail("The Timeline start-time set variant carries a stale revision.")

    if descriptor.family == "multi_target":
        if authority.get("closedComposition") is not True:
            _fail("Multi-target mutation impact must be a closed composition.")
    if descriptor.command_id == "timeline.sync_clips":
        affected_track_types = authority.get("affectedTrackTypes")
        sync_plan_digest = authority.get("syncPlanDigest")
        if (
            authority.get("syncPlacementPlanComplete") is not True
            or authority.get("privateExecutionProfile") != "sdk_timeline_sync_exact_v1"
            or not isinstance(affected_track_types, list)
            or not affected_track_types
            or any(
                track_type not in {"video", "audio"}
                for track_type in affected_track_types
            )
            or len(set(affected_track_types)) != len(affected_track_types)
            or not isinstance(sync_plan_digest, str)
            or not sync_plan_digest.startswith("sha256:")
            or len(sync_plan_digest) != 71
        ):
            _fail(
                "Timeline synchronization requires one complete exact placement plan."
            )
    if (
        descriptor.linked_topology
        and authority.get("linkedTopologyComplete") is not True
    ):
        _fail("Complete reciprocal linked topology is required before authorization.")
    if (
        descriptor.artifact_destination
        and authority.get("artifactDestinationExact") is not True
    ):
        _fail("The managed artifact destination is ambiguous or incomplete.")
    if descriptor.family == "version":
        if authority.get("durableWorkflowAuthority") != "sdk_workflow_v1":
            _fail("Version mutation requires the durable SDK workflow authority.")
        if descriptor.command_id == "version.restore":
            if authority.get("resolvedCheckpointId") != input_value.get("checkpointId"):
                _fail(
                    "Version restore checkpoint identity is missing, ambiguous, or stale."
                )
            if not _non_empty_text(authority.get("expectedCurrentStateHash")):
                _fail("Version restore requires the exact current project state hash.")
            if authority.get("projectStateHash") != authority.get(
                "expectedCurrentStateHash"
            ):
                _fail("Version restore current project state is stale.")
            if not _sha256_digest(authority.get("checkpointBindingDigest")):
                _fail("Version restore checkpoint contents are not durably bound.")
            checkpoint_session_id = authority.get("resolvedCheckpointSessionId")
            if not _non_empty_text(checkpoint_session_id):
                _fail("Version restore checkpoint owner is not durably bound.")
            if (
                input_value.get("sessionId") is not None
                and input_value.get("sessionId") != checkpoint_session_id
            ):
                _fail("Version restore checkpoint owner is stale.")
        if (
            descriptor.command_id == "version.create"
            and input_value.get("parentCheckpointId") is not None
        ):
            if authority.get("resolvedParentCheckpointId") != input_value.get(
                "parentCheckpointId"
            ):
                _fail("Version create parent checkpoint identity is stale.")
            if not _sha256_digest(authority.get("parentCheckpointBindingDigest")):
                _fail(
                    "Version create parent checkpoint contents are not durably bound."
                )
        if (
            descriptor.command_id == "version.prune"
            and authority.get("checkpointHistoryComplete") is not True
        ):
            _fail("Version prune requires the complete retained checkpoint history.")
        if descriptor.command_id == "version.prune":
            checkpoint_ids = authority.get("resolvedCheckpointIds")
            if (
                not isinstance(checkpoint_ids, list)
                or not checkpoint_ids
                or any(
                    not _non_empty_text(checkpoint_id)
                    for checkpoint_id in checkpoint_ids
                )
            ):
                _fail(
                    "Version prune requires the exact non-empty checkpoint deletion set."
                )
            if len(set(checkpoint_ids)) != len(checkpoint_ids):
                _fail("Version prune checkpoint identities must be unique.")

    targets = _exact_targets(descriptor, input_value, authority)
    if descriptor.command_id == "timeline.sync_clips":
        timeline_targets = [
            target for target in targets if target.get("kind") == "timeline"
        ]
        if (
            len(timeline_targets) != 1
            or timeline_targets[0].get("publicId") != timeline["id"]
            or timeline_targets[0].get("revision") != timeline["revision"]
        ):
            _fail(
                "Timeline synchronization requires exactly one live bound Timeline target."
            )
    pre_state = _private_pre_state(descriptor, project, timeline, targets, authority)
    if descriptor.checkpoint_policy == "checkpoint_restore":
        if not _non_empty_text(authority.get("checkpointId")):
            _fail("Timeline mutation requires a durable pre-mutation checkpoint.")
        if authority.get("checkpointProjectId") != project["id"]:
            _fail("The recovery checkpoint is not bound to the exact live project.")
        if (
            timeline is not None
            and authority.get("checkpointTimelineId") != timeline["id"]
        ):
            _fail("The recovery checkpoint is not bound to the exact live timeline.")

    return MappingProxyType(
        {
            "actionId": descriptor.action_id,
            "family": descriptor.family,
            "bindingLevel": descriptor.binding_level,
            "effectKind": descriptor.effect_kind,
            "projectId": project["id"],
            "projectRevision": project["revision"],
            **(
                {"timelineId": timeline["id"], "timelineRevision": timeline["revision"]}
                if timeline is not None
                else {}
            ),
            "resolvedTargets": targets,
            "privateCanonicalPreState": pre_state,
            "closedComposition": True,
            "executableStableTargetPrecondition": True,
            "checkpointPolicy": descriptor.checkpoint_policy,
            **(
                {"checkpointId": authority["checkpointId"]}
                if descriptor.checkpoint_policy == "checkpoint_restore"
                else {}
            ),
            **(
                {"workflowCheckpointAuthority": "sdk_workflow_v1"}
                if descriptor.family == "version"
                else {}
            ),
            **(
                {
                    "resolvedCheckpointIds": tuple(
                        sorted(
                            str(value) for value in authority["resolvedCheckpointIds"]
                        )
                    )
                }
                if descriptor.command_id == "version.prune"
                else {}
            ),
            **(
                {"expectedCurrentStateHash": authority["expectedCurrentStateHash"]}
                if descriptor.command_id == "version.restore"
                else {}
            ),
            **(
                {"checkpointBindingDigest": authority["checkpointBindingDigest"]}
                if descriptor.command_id == "version.restore"
                else {}
            ),
            **(
                {"checkpointSessionId": authority["resolvedCheckpointSessionId"]}
                if descriptor.command_id == "version.restore"
                else {}
            ),
            **(
                {
                    "parentCheckpointBindingDigest": authority[
                        "parentCheckpointBindingDigest"
                    ]
                }
                if descriptor.command_id == "version.create"
                and input_value.get("parentCheckpointId") is not None
                else {}
            ),
            **(
                {
                    "syncPlanDigest": authority["syncPlanDigest"],
                    "affectedTrackTypes": tuple(
                        sorted(authority["affectedTrackTypes"])
                    ),
                    "privateExecutionProfile": "sdk_timeline_sync_exact_v1",
                }
                if descriptor.command_id == "timeline.sync_clips"
                else {}
            ),
            "protectedState": descriptor.protected_state,
            "minimumEvidence": descriptor.minimum_evidence,
            "recovery": descriptor.recovery,
        }
    )


def public_timeline_version_policy_effect(
    prepared: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Project one strict public Mutation Policy effect without private lowering."""

    action_id = prepared.get("actionId")
    descriptor = TIMELINE_VERSION_MUTATION_DESCRIPTORS.get(str(action_id))
    if descriptor is None:
        _fail("Prepared action is not owned by this descriptor packet.")
    public_targets = []
    for target in prepared.get("resolvedTargets", ()):
        if (
            descriptor.command_id == "timeline.sync_clips"
            and target.get("kind") != "timeline"
        ):
            continue
        public_targets.append(
            {
                key: target[key]
                for key in (
                    "kind",
                    "stableId",
                    "revision",
                    "trackType",
                    "trackIndex",
                    "mediaRole",
                )
                if key in target
            }
        )
    return MappingProxyType(
        {
            "operation": descriptor.command_id,
            "kind": (
                "update"
                if descriptor.command_id == "version.prune"
                else "create"
                if descriptor.effect_kind == "artifact"
                else descriptor.effect_kind
            ),
            "trackTypes": (
                list(prepared["affectedTrackTypes"])
                if descriptor.command_id == "timeline.sync_clips"
                else sorted(
                    {
                        str(target["trackType"])
                        for target in public_targets
                        if target.get("trackType") in {"video", "audio", "subtitle"}
                    }
                )
            ),
            "targets": tuple(public_targets),
            "placementIntent": "explicit",
            "broad": False,
            "ambiguous": False,
            "complete": True,
        }
    )


def authorize_prepared_timeline_version_action(
    action_id: str,
    input_value: Mapping[str, Any],
    authority: Mapping[str, Any],
    authorize: Any,
) -> Any:
    """Prove that descriptor admission always precedes the authorization call."""

    prepared = prepare_timeline_version_action(action_id, input_value, authority)
    return authorize(prepared)


def verify_timeline_version_protected_state(
    prepared: Mapping[str, Any], evidence: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Require exact target outcome and every declared protected-state family."""

    protected = evidence.get("protectedState")
    required = tuple(prepared.get("protectedState", ()))
    missing = [
        name
        for name in required
        if not isinstance(protected, Mapping) or protected.get(name) is not True
    ]
    modalities = set(evidence.get("modalities", ()))
    missing_modalities = [
        name for name in prepared.get("minimumEvidence", ()) if name not in modalities
    ]
    passed = (
        evidence.get("targetMatched") is True
        and evidence.get("authorizationBound") is True
        and not missing
        and not missing_modalities
    )
    return MappingProxyType(
        {
            "outcome": "passed" if passed else "failed",
            "protectedStatePreserved": not missing,
            "missingProtectedState": tuple(missing),
            "missingEvidence": tuple(missing_modalities),
        }
    )


def evaluate_timeline_version_recovery(
    prepared: Mapping[str, Any],
    *,
    possible_mutation: Literal["none", "possible", "partial", "confirmed"],
    restore_evidence: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    """Project truthful checkpoint restoration without inventing success."""

    if possible_mutation == "none":
        return MappingProxyType(
            {"status": "not_needed", "manualRecoveryRequired": False}
        )
    if prepared.get("checkpointPolicy") != "checkpoint_restore":
        return MappingProxyType(
            {
                "status": "manual_required",
                "manualRecoveryRequired": True,
                "reason": "The descriptor is governed by checkpoint-history or workflow authority.",
            }
        )
    restored = bool(
        isinstance(restore_evidence, Mapping)
        and restore_evidence.get("checkpointId") == prepared.get("checkpointId")
        and restore_evidence.get("projectId") == prepared.get("projectId")
        and restore_evidence.get("timelineId") == prepared.get("timelineId")
        and restore_evidence.get("readbackMatched") is True
        and restore_evidence.get("protectedStatePreserved") is True
        and restore_evidence.get("protectedStateDigest")
        == prepared.get("privateCanonicalPreState", {}).get("protectedStateDigest")
    )
    return MappingProxyType(
        {
            "status": "restored" if restored else "failed",
            "manualRecoveryRequired": not restored,
        }
    )


def public_timeline_version_descriptor_summary() -> dict[str, Any]:
    """Return the only descriptor projection allowed outside the private runtime."""

    actions = []
    for descriptor in sorted(_DESCRIPTORS, key=lambda row: row.action_id):
        actions.append(
            {
                "actionId": descriptor.action_id,
                "family": descriptor.family,
                "bindingLevel": descriptor.binding_level,
                "effectKind": descriptor.effect_kind,
                "targetKinds": list(descriptor.target_kinds),
                "targetCardinality": descriptor.target_cardinality,
                **(
                    {"fixedTrackType": descriptor.fixed_track_type}
                    if descriptor.fixed_track_type is not None
                    else {}
                ),
                "requiresExactTargets": True,
                "requiresExactTrack": descriptor.exact_track,
                "requiresExactArtifactDestination": descriptor.artifact_destination,
                "requiresProjectControlsDisabled": (
                    descriptor.command_id == "timeline.dolby.analyze"
                ),
                "forbidsTimelineCreation": (
                    descriptor.command_id == "timeline.sync_clips"
                ),
                "requiresExactPlacementPlan": (
                    descriptor.command_id == "timeline.sync_clips"
                ),
                "requiresClosedComposition": descriptor.closed_composition,
                "requiresLinkedTopology": descriptor.linked_topology,
                **(
                    {"operationVariant": descriptor.operation_variant}
                    if descriptor.operation_variant is not None
                    else {}
                ),
                "checkpointPolicy": descriptor.checkpoint_policy,
                "protectedState": list(descriptor.protected_state),
                "minimumEvidence": list(descriptor.minimum_evidence),
                "recovery": descriptor.recovery,
            }
        )
    return {
        "schemaVersion": 1,
        "packet": "timeline_version_mutations_v1",
        "counts": {"total": 44, "stable": 35, "multiTarget": 6, "version": 3},
        "actions": actions,
    }
