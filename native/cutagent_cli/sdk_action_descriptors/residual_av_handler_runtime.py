"""Exact lowering of residual AV actions to authoritative CLI handlers.

Every action is hard-bound to the existing command-catalog handler. Execution is
owned by the carrier-injected process authority so this module cannot mint or
simulate signed-carrier admission.
"""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import importlib
import inspect
import json
import re
from types import MappingProxyType
from typing import Any, Callable, Mapping

import typer

from ..command_catalog import get_command_catalog
from ..errors import ValidationError
from ..output import capture_prepared_action_output
from ..policy import _prepared_action_admission_scope
from .residual_av import RESIDUAL_AV_ACTION_DESCRIPTORS


_ALIASES = MappingProxyType(
    {
        "audio.beat_detect": {"inputPath": "input"},
        "audio.duck": {
            "inputPath": "input_media",
            "speechTrackIndex": "speech_track",
            "musicTrackIndex": "music_track",
            "outputPath": "output_file",
            "replaceMediaName": "replace_media",
        },
        "audio.info": {"inputPath": "input"},
        "audio.probe_subframe": {},
        "audio.reverb": {"inputPath": "input", "outputPath": "output_file"},
        "audio.waveform_offset": {
            "referencePath": "reference",
            "targetPath": "target",
            "windowCount": "windows",
        },
        "burnin.load": {"presetName": "name"},
        "burnin.preset.export": {"presetName": "name", "outputPath": "path"},
        "burnin.preset.import": {"inputPath": "path"},
        "clip.fusion.list": {"clipName": "name", "videoTrackIndex": "track"},
        "clip.linked.list": {"clipName": "clip"},
        "clip.offset": {"clipName": "name"},
        "clip.smart_reframe": {
            "clipName": "name",
            "timelineItemId": "item_id",
            "trackIndex": "track",
        },
        "clip.source_range": {"clipName": "clip"},
        "clip.take.list": {"clipName": "name"},
        "clip.track_info": {"clipName": "clip"},
        "text.insert": {
            "text": "text_option",
            "recordPosition": "at",
            "videoTrackIndex": "track",
            "clipName": "name",
        },
        "text.insert_preset": {
            "presetName": "name",
            "text": "text_option",
            "recordPosition": "at",
            "videoTrackIndex": "track",
        },
        "text.insert_template": {
            "templatePath": "template",
            "text": "text_option",
            "imagePath": "image",
            "clipName": "name",
            "recordPosition": "at",
            "videoTrackIndex": "track",
            "containerKind": "holder_kind",
            "containerPreset": "holder",
        },
        "text.update": {
            "text": "text_option",
            "recordPosition": "record_frame",
            "videoTrackIndex": "track",
            "toolName": "tool",
        },
    }
)

# Handler names are private execution authority, not public command metadata.
# Public packaged-runtime snapshots intentionally omit them, so the closed
# prepared-action runtime carries the exact reviewed binding itself.
_PRIVATE_HANDLER_FUNCTIONS = MappingProxyType(
    {
        "audio.beat_detect": "beat_detect",
        "audio.duck": "duck",
        "audio.info": "info",
        "audio.probe_subframe": "probe_subframe",
        "audio.reverb": "reverb",
        "audio.waveform_offset": "waveform_offset",
        "burnin.load": "load",
        "burnin.preset.export": "preset_export",
        "burnin.preset.import": "preset_import",
        "clip.audio_eq": "clip_audio_eq",
        "clip.audio_gain": "clip_audio_gain",
        "clip.audio_normalize": "clip_audio_normalize",
        "clip.audio_pan": "clip_audio_pan",
        "clip.audio_pitch": "clip_audio_pitch",
        "clip.burnin.load": "burnin_load",
        "clip.cache": "clip_cache",
        "clip.cache_set": "cache_set",
        "clip.color": "clip_color",
        "clip.composite": "clip_composite",
        "clip.disable": "disable_clip",
        "clip.dynamic_zoom": "dynamic_zoom",
        "clip.enable": "enable_clip",
        "clip.fade_in": "clip_fade_in",
        "clip.flag": "clip_flag",
        "clip.fusion.add": "fusion_add",
        "clip.fusion.delete": "fusion_delete",
        "clip.fusion.export": "fusion_export",
        "clip.fusion.import": "fusion_import",
        "clip.fusion.list": "fusion_list",
        "clip.fusion.load": "fusion_load",
        "clip.fusion.tool_set": "fusion_tool_set",
        "clip.link": "link_clips",
        "clip.linked.list": "linked_list",
        "clip.magic_mask": "magic_mask_clip",
        "clip.marker.add": "marker_add",
        "clip.marker.custom_data": "marker_custom_data",
        "clip.marker.delete": "marker_delete",
        "clip.marker.delete_custom": "marker_delete_custom",
        "clip.offset": "clip_offset",
        "clip.properties": "clip_properties",
        "clip.rename": "rename_clip",
        "clip.reset_node_colors": "reset_node_colors",
        "clip.smart_reframe": "smart_reframe_clip",
        "clip.source_range": "source_range",
        "clip.stabilize": "stabilize_clip",
        "clip.take.add": "take_add",
        "clip.take.delete": "take_delete",
        "clip.take.finalize": "take_finalize",
        "clip.take.list": "take_list",
        "clip.take.select": "take_select",
        "clip.track_info": "track_info",
        "clip.unlink": "unlink_clip",
        "clip.update_sidecar": "update_sidecar",
        "clip.voice_isolation": "voice_isolation_clip",
        "edit.auto_subtitle": "auto_subtitle",
        "edit.camera_pip": "camera_pip",
        "edit.delete_through_edit": "delete_through_edit",
        "edit.from_edl": "from_edl",
        "edit.remove": "remove",
        "edit.remove_range": "remove_range",
        "edit.ripple_delete": "ripple_delete",
        "edit.ripple_delete_selected": "ripple_delete_selected",
        "edit.scene_detect": "scene_detect",
        "edit.slide_selected": "slide_selected",
        "edit.slip_selected": "slip_selected",
        "edit.social_crop": "social_crop",
        "edit.split": "split",
        "edit.transition.add": "transition_add",
        "edit.transition.batch": "transition_batch",
        "text.insert": "insert",
        "text.insert_preset": "insert_preset",
        "text.insert_template": "insert_template",
        "text.insert_template_batch": "insert_template_batch",
        "text.update": "update",
    }
)


def _edit_handler_input(command_id: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """Lower reviewed Edit semantics without exposing the handler contract publicly."""

    def frame(number):
        return f"{int(number)}f"
    target = value.get("target") if isinstance(value.get("target"), Mapping) else None
    targets = value.get("targets") if isinstance(value.get("targets"), list) else []
    first = target or (targets[0] if targets else None)
    if command_id == "edit.auto_subtitle":
        return {
            "language": value.get("language"),
            "preset": value.get("preset"),
            "chars_per_line": value.get("charsPerLine"),
            "line_break": value.get("lineBreak"),
            "gap": value.get("gapFrames"),
        }
    if command_id == "edit.camera_pip":
        camera, background = value["cameraMedia"], value.get("backgroundMedia")
        return {
            "camera_clip": camera["name"],
            "background_clip": background["name"] if background else None,
            "at": frame(value["recordStartFrame"]),
            "duration": frame(value["durationFrames"]),
            "camera_track": value["cameraTrackIndex"],
            "background_track": value["backgroundTrackIndex"],
            "zoom": value.get("zoom"),
            "pan": value.get("pan"),
            "tilt": value.get("tilt"),
            "anchor": value.get("anchor"),
            "margin": value.get("marginPixels"),
            "verify_placement": True,
            # The residual production verifier owns rendered-frame evidence. The
            # catalog handler's optional visual check requires an anchor and
            # must not silently widen the public input contract.
            "verify_rendered_placement": False,
            "corner_radius": value.get("cornerRadius"),
            "softness": value.get("softness"),
            "opacity": value.get("opacity"),
        }
    if command_id == "edit.delete_through_edit":
        return {
            "at": frame(value["editFrame"]),
            "track_type": value["outgoing"]["trackType"],
            "track_index": value["outgoing"]["trackIndex"],
            "tolerance_frames": value.get("editFrameTolerance"),
        }
    if command_id == "edit.from_edl":
        return {"path": value.get("inputPath", value["inputArtifactId"])}
    if command_id == "edit.remove":
        return {
            "at": frame(value["recordFrame"]),
            "track_type": target["trackType"],
            "track_index": target["trackIndex"],
        }
    if command_id == "edit.remove_range":
        return {
            "in_pos": frame(value["rangeStartFrame"]),
            "out_pos": frame(value["rangeEndFrameExclusive"]),
            "track_type": first["trackType"],
            "track_index": first["trackIndex"],
        }
    if command_id == "edit.ripple_delete":
        return {
            "at": frame(value["rangeStartFrame"]),
            "duration": frame(
                value["rangeEndFrameExclusive"] - value["rangeStartFrame"]
            ),
            "fps": value["timelineFrameRate"],
            "timeline_name": value["newTimelineName"],
        }
    if command_id == "edit.ripple_delete_selected":
        return {
            "clip_name": target["name"],
            "at": frame(value["recordFrame"]),
            "track_type": value["scope"],
        }
    if command_id == "edit.scene_detect":
        return {}
    if command_id in {"edit.slide_selected", "edit.slip_selected"}:
        return {
            "clip_name": target["name"],
            "at": frame(value["recordFrame"]),
            "direction": value["direction"],
            "steps": value["steps"],
        }
    if command_id == "edit.social_crop":
        return {
            "clip_name": first["name"] if len(targets) == 1 else None,
            "format_name": value["format"],
            "source_aspect": value["sourceAspect"],
            "pan": value.get("pan"),
            "tilt": value.get("tilt"),
            "zoom": value.get("zoom"),
            "all_clips": len(targets) > 1,
            "set_timeline": value["setTimelineResolution"],
        }
    if command_id == "edit.split":
        cuts = [
            {
                "at": frame(value["recordFrame"]),
                "track_type": item["trackType"],
                "track_index": item["trackIndex"],
            }
            for item in targets
        ]
        return {
            "batch_json": json.dumps(
                {"cuts": cuts}, separators=(",", ":"), sort_keys=True
            ),
            "allow_partial": False,
            "respect_locks": True,
        }
    if command_id == "edit.transition.add":
        placement = value["placement"]
        # The CLI uses --at both to resolve the selected clip (half-open range)
        # and, for a centered transition, as the seam. Select the incoming side
        # at its inclusive start for start/center placement. End placement is
        # relative to the outgoing clip, so select its final included frame.
        primary = value["outgoing"] if placement == "end" else value["incoming"]
        selector_frame = value["editFrame"] - 1 if placement == "end" else value["editFrame"]
        timeline_start_frame = int(value.get("timelineStartFrame", 0))
        return {
            "transition_type": value["transitionType"],
            "duration": frame(value["durationFrames"]),
            # CutAgent CLI record-frame inputs are timeline-relative; the SDK's
            # editFrame is the absolute record coordinate from the snapshot.
            "at": frame(selector_frame - timeline_start_frame),
            "clip_name": primary["name"],
            "placement": placement,
            "scope": value["scope"],
        }
    if command_id == "edit.transition.batch":
        requested = value["transitions"]
        transitions = requested if isinstance(requested, list) else [requested]
        entries = []
        for index, transition in enumerate(transitions):
            placement = transition["placement"]
            primary = (
                transition["outgoing"]
                if placement == "end"
                else transition["incoming"]
            )
            entries.append(
                {
                    "index": index,
                    "track_type": "video",
                    "track_index": primary["trackIndex"],
                    "name": primary["name"],
                    "start_frame": primary["recordStartFrame"],
                    "end_frame": primary["recordEndFrame"],
                    "at_frame": transition["editFrame"],
                    "transition_type": transition["transitionType"],
                    "duration_frames": transition["durationFrames"],
                    "placement": placement,
                    "scope": "video",
                }
            )
        return {
            "batch_json": json.dumps(
                {"entries": entries}, separators=(",", ":"), sort_keys=True
            ),
            "allow_partial": False,
            "scope": "video",
        }
    raise ValidationError("Prepared Edit action lacks private lowering.")


def _snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _catalog_bindings() -> Mapping[str, tuple[str, str]]:
    catalog = {command.command_id: command for command in get_command_catalog()}
    expected_command_ids = {descriptor.command_id for descriptor in RESIDUAL_AV_ACTION_DESCRIPTORS}
    if set(_PRIVATE_HANDLER_FUNCTIONS) != expected_command_ids:
        raise RuntimeError("Residual private handler binding partition drifted.")
    result: dict[str, tuple[str, str]] = {}
    for descriptor in RESIDUAL_AV_ACTION_DESCRIPTORS:
        command = catalog.get(descriptor.command_id)
        function_name = _PRIVATE_HANDLER_FUNCTIONS[descriptor.command_id]
        if command is None or (
            command.function_name and command.function_name != function_name
        ):
            raise RuntimeError(
                f"Residual action lacks an authoritative command handler: {descriptor.action_id}"
            )
        root = command.path.split()[0]
        result[descriptor.action_id] = (
            f"cutagent_cli.commands.{root}",
            function_name,
        )
    return MappingProxyType(result)


RESIDUAL_AV_HANDLER_BINDINGS = _catalog_bindings()


class ResidualAvHandlerExecutionAuthority:
    """Carrier-admitted process authority for exact catalog handler execution."""

    def __init__(
        self,
        *,
        resolve_exact: Callable[..., Mapping[str, Any]],
        resolve_managed_artifact: Callable[[str], Mapping[str, Any]],
        recover: Callable[..., Mapping[str, Any]],
    ):
        for callback in (resolve_exact, resolve_managed_artifact, recover):
            if not callable(callback):
                raise TypeError("Residual AV authority callbacks must be callable.")
        self._resolve_exact = resolve_exact
        self._resolve_managed_artifact = resolve_managed_artifact
        self._recover = recover

    def resolve_exact(self, action_id, context, value, *, phase):
        return self._resolve_exact(action_id, context, value, phase=phase)

    def resolve_managed_artifact(self, input_path):
        return self._resolve_managed_artifact(input_path)

    def recover(self, action_id, context, prepared, failure):
        return self._recover(action_id, context, prepared, failure)

    def _matches_carrier_admission(
        self, action_id: str, command_id: str, admitted_handler: object
    ) -> bool:
        binding = RESIDUAL_AV_HANDLER_BINDINGS.get(action_id)
        descriptor = next(
            (
                item
                for item in RESIDUAL_AV_ACTION_DESCRIPTORS
                if item.action_id == action_id
            ),
            None,
        )
        if binding is None or descriptor is None or descriptor.command_id != command_id:
            return False
        module = importlib.import_module(binding[0])
        handler = getattr(module, binding[1], None)
        return (
            callable(handler)
            and inspect.unwrap(handler) is admitted_handler
        )

    def invoke_admitted_handler(self, action_id, context, prepared, handler_input):
        if context.get("executionAuthority") is not self:
            raise ValidationError("Residual handler lacks carrier admission authority.")
        binding = RESIDUAL_AV_HANDLER_BINDINGS.get(action_id)
        descriptor = next(
            (
                item
                for item in RESIDUAL_AV_ACTION_DESCRIPTORS
                if item.action_id == action_id
            ),
            None,
        )
        lowering = prepared.get("domain", {}).get("lowering")
        if binding is None or descriptor is None or not isinstance(lowering, Mapping):
            raise ValidationError("Residual handler has no exact prepared binding.")
        expected_args = canonical_residual_av_handler_args(action_id, handler_input)
        if (
            lowering.get("commandId") != descriptor.command_id
            or lowering.get("args") != expected_args
        ):
            raise ValidationError(
                "Residual handler drifted from its prepared command binding."
            )
        module = importlib.import_module(binding[0])
        wrapped = getattr(module, binding[1], None)
        if not callable(wrapped):
            raise RuntimeError(
                f"Catalog handler is unavailable: {descriptor.command_id}"
            )
        function = inspect.unwrap(wrapped)
        kwargs = _handler_kwargs(descriptor.command_id, function, handler_input)
        with ExitStack() as stack:
            captured = stack.enter_context(capture_prepared_action_output())
            stack.enter_context(
                _prepared_action_admission_scope(
                    action_id, descriptor.command_id, self, function, context
                )
            )
            returned = function(**kwargs)
        if len(captured) > 1:
            raise ValidationError(
                "Authoritative handler emitted multiple terminal results."
            )
        if captured:
            return captured[0]
        if returned is not None:
            return returned
        raise ValidationError("Authoritative handler emitted no inspectable result.")


def _default_value(parameter: inspect.Parameter) -> Any:
    default = parameter.default
    if isinstance(default, (typer.models.ArgumentInfo, typer.models.OptionInfo)):
        default = default.default
    if default is ...:
        raise ValidationError(
            f"Prepared action omitted required handler input: {parameter.name}"
        )
    if default is inspect.Parameter.empty:
        raise ValidationError(
            f"Prepared action omitted required handler input: {parameter.name}"
        )
    return deepcopy(default)


def _handler_kwargs(
    command_id: str, function, value: Mapping[str, Any]
) -> dict[str, Any]:
    aliases = _ALIASES.get(command_id, {})
    supplied: dict[str, Any] = {}
    if command_id.startswith("edit."):
        supplied.update(
            {
                key: item
                for key, item in _edit_handler_input(command_id, value).items()
                if item is not None
            }
        )
    if command_id == "text.insert_template_batch":
        field_names = {
            "templatePath": "template",
            "videoTrackIndex": "track",
            "trackPolicy": "track_policy",
            "allowCreateTrack": "allow_create_track",
            "allowNonEmptyTrack": "allow_non_empty_track",
            "requireAboveOccupied": "require_above_occupied",
            "cleanupOnFailure": "cleanup_on_failure",
            "containerKind": "holder_kind",
            "containerPreset": "holder",
            "styleMarkdown": "style_markdown",
            "boldStyle": "bold_style",
            "requireText": "require_text",
            "requireImage": "require_image",
            "requireStyling": "require_styling",
            "imagePath": "image",
            "replacements": "params",
        }
        spec = {
            field_names[name]: deepcopy(field_value)
            for name, field_value in value.items()
            if name != "items"
        }
        spec["items"] = [
            {
                {
                    "recordPosition": "at",
                    "clipName": "name",
                    "imagePath": "image",
                    "replacements": "params",
                }.get(name, name): deepcopy(field_value)
                for name, field_value in item.items()
            }
            for item in value["items"]
        ]
        supplied["spec_json"] = json.dumps(spec, separators=(",", ":"), sort_keys=True)
    for public_name, public_value in value.items():
        if command_id.startswith("edit."):
            continue
        if command_id == "text.insert_template_batch":
            continue
        python_name = aliases.get(public_name, _snake(public_name))
        if python_name in supplied:
            raise ValidationError("Prepared action handler input aliases collide.")
        supplied[python_name] = deepcopy(public_value)
    signature = inspect.signature(function)
    unknown = set(supplied) - set(signature.parameters)
    if unknown:
        raise ValidationError(
            f"Prepared action contains inputs not owned by its handler: {sorted(unknown)}"
        )
    return {
        name: supplied[name] if name in supplied else _default_value(parameter)
        for name, parameter in signature.parameters.items()
    }


def canonical_residual_av_handler_args(
    action_id: str, value: Mapping[str, Any]
) -> list[str]:
    """Return a private deterministic lowering for receipt/impact binding."""

    binding = RESIDUAL_AV_HANDLER_BINDINGS.get(action_id)
    if binding is None:
        raise ValidationError("Residual action has no authoritative handler binding.")
    descriptor = next(
        item for item in RESIDUAL_AV_ACTION_DESCRIPTORS if item.action_id == action_id
    )
    module = importlib.import_module(binding[0])
    function = inspect.unwrap(getattr(module, binding[1]))
    kwargs = _handler_kwargs(descriptor.command_id, function, value)
    return [
        f"--{name.replace('_', '-')}={json.dumps(kwargs[name], separators=(',', ':'), sort_keys=True)}"
        for name in inspect.signature(function).parameters
    ]


def validate_residual_av_handler_bindings() -> None:
    expected = {item.action_id for item in RESIDUAL_AV_ACTION_DESCRIPTORS}
    if set(RESIDUAL_AV_HANDLER_BINDINGS) != expected:
        raise RuntimeError("Residual handler bindings do not close exact ownership.")


validate_residual_av_handler_bindings()
