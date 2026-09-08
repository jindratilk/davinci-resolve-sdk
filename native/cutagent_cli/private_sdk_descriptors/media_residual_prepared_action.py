"""Signed exact-lifecycle owners for the remaining supported Media mutations."""

from __future__ import annotations

from contextlib import ExitStack
from collections import Counter
from copy import deepcopy
import csv
from dataclasses import dataclass
import importlib
import inspect
import hashlib
import io
import json
from pathlib import Path
import subprocess
from types import MappingProxyType
from typing import Any, Mapping

from .._sdk_prepared_action_contract import PREPARED_ACTION_ACTION_METADATA
from ..command_catalog import get_command_catalog
from ..connection import get_connection
from ..core import media_pool
from ..errors import APICallFailed, ValidationError
from ..external_tools import resolve_tool
from ..output import capture_prepared_action_output
from ..policy import _prepared_action_admission_scope
from ..sdk_action_descriptors.residual_av_handler_runtime import _handler_kwargs
from .project_media_extended_prepared_action import (
    _SEMANTIC_METADATA_NATIVE_KEYS,
    _clip_by_public_id,
    _media_applicability,
    _media_state,
    _sdk_digest,
)
from .project_render_storage_media_prepared_action import (
    _assert_native_project_binding,
    _assert_public,
    _canonical,
    _digest,
    _impact,
    _project_binding,
)


MEDIA_RESIDUAL_CALLABLE_ACTION_IDS = (
    "cutagent.action.media.clear_transcription", "cutagent.action.media.color.clear",
    "cutagent.action.media.color.set", "cutagent.action.media.create_timeline",
    "cutagent.action.media.delete", "cutagent.action.media.duplicate",
    "cutagent.action.media.extract_template", "cutagent.action.media.flag.add",
    "cutagent.action.media.flag.clear", "cutagent.action.media.folder.export_drb",
    "cutagent.action.media.folder.import_drb", "cutagent.action.media.folders.move",
    "cutagent.action.media.folders.open", "cutagent.action.media.folders.root",
    "cutagent.action.media.growing_file.monitor", "cutagent.action.media.mark.clear",
    "cutagent.action.media.mark.set", "cutagent.action.media.marker.add",
    "cutagent.action.media.marker.delete", "cutagent.action.media.matte.delete",
    "cutagent.action.media.metadata.export", "cutagent.action.media.move",
    "cutagent.action.media.proxy", "cutagent.action.media.proxy.link_fullres",
    "cutagent.action.media.relink", "cutagent.action.media.rename",
    "cutagent.action.media.replace", "cutagent.action.media.replace_preserve_subclip",
    "cutagent.action.media.selected.set", "cutagent.action.media.stereo_create",
    "cutagent.action.media.sync_audio", "cutagent.action.media.transcode",
    "cutagent.action.media.transcribe", "cutagent.action.media.unlink",
)

# Handler names are private execution authority, not public command metadata.
# Public compiled-runtime catalog snapshots intentionally omit them, so the
# proprietary prepared-action runtime carries the reviewed binding itself.
_PRIVATE_MEDIA_HANDLER_FUNCTIONS = MappingProxyType(
    {
        "media.clear_transcription": "clear_transcription_cmd",
        "media.color.clear": "color_clear",
        "media.color.set": "color_set",
        "media.create_timeline": "create_timeline",
        "media.delete": "delete_clip",
        "media.duplicate": "duplicate_clip",
        "media.extract_template": "extract_template",
        "media.flag.add": "flag_add",
        "media.flag.clear": "flag_clear",
        "media.folder.export_drb": "folder_export_drb",
        "media.folder.import_drb": "folder_import_drb",
        "media.folders.move": "folders_move",
        "media.folders.open": "folders_open",
        "media.folders.root": "folders_root",
        "media.growing_file.monitor": "growing_file_monitor",
        "media.mark.clear": "mark_clear",
        "media.mark.set": "mark_set",
        "media.marker.add": "marker_add",
        "media.marker.delete": "marker_delete",
        "media.matte.delete": "matte_delete",
        "media.metadata.export": "metadata",
        "media.move": "move_clip",
        "media.proxy": "proxy_clip",
        "media.proxy.link_fullres": "proxy_link_fullres",
        "media.relink": "relink_clip",
        "media.rename": "rename",
        "media.replace": "replace",
        "media.replace_preserve_subclip": "replace_preserve_subclip",
        "media.selected.set": "selected_set",
        "media.stereo_create": "stereo_create",
        "media.sync_audio": "sync_audio_cmd",
        "media.transcode": "transcode_clip",
        "media.transcribe": "transcribe_cmd",
        "media.unlink": "unlink_clip",
    }
)

if set(_PRIVATE_MEDIA_HANDLER_FUNCTIONS) != {
    action_id.removeprefix("cutagent.action.")
    for action_id in MEDIA_RESIDUAL_CALLABLE_ACTION_IDS
}:
    raise RuntimeError("Private Media handler binding partition drifted.")


def _tag_execution_failure(failure: BaseException, phase: str) -> None:
    try:
        failure.prepared_action_substage = phase
    except Exception:
        pass


def _binding(context: Mapping[str, Any]) -> dict[str, Any]:
    private = context.get("privateBindings")
    media = private.get("mediaPool") if isinstance(private, Mapping) else None
    required = {"operation", "revision", "targets", "handlerInput", "artifacts"}
    if not isinstance(media, Mapping) or set(media) != required or media.get("operation") != "generic":
        raise ValidationError("Prepared Media action omitted its carrier-owned exact binding.")
    targets = media.get("targets")
    if not isinstance(targets, (list, tuple)) or not targets or any(
        not isinstance(row, Mapping) or not isinstance(row.get("id"), str) for row in targets
    ):
        raise ValidationError("Prepared Media action has malformed exact targets.")
    if len({row["id"] for row in targets}) != len(targets):
        raise ValidationError("Prepared Media action target binding is ambiguous.")
    # The signed authority freezes carrier JSON arrays as tuples and objects as
    # mapping proxies. Thaw only this already-validated Media binding into the
    # descriptor's private working copy; the runtime context remains immutable.
    return _canonical(media)


def _handler_input(action_id: str, value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if action_id == "cutagent.action.media.proxy":
        operation = result.pop("operation")
        result = {
            "name": result.pop("clipName"), "generate": operation["kind"] == "generate",
            "link": operation.get("path"), "unlink": operation["kind"] == "unlink",
        }
    elif action_id == "cutagent.action.media.metadata.export":
        result = {"args": ["export", result["file"], *result.get("clips", [])]}
    if action_id == "cutagent.action.media.delete":
        result["force"] = True
    if action_id == "cutagent.action.media.proxy.link_fullres":
        result["ctx"] = None
        result["dry_run"] = False
        result["json_output"] = False
    return result


def _assert_proxy_generation_capability(
    conn: Any,
    project_id: str,
    binding: Mapping[str, Any],
    value: Mapping[str, Any],
) -> None:
    operation = value.get("operation")
    if not isinstance(operation, Mapping) or operation.get("kind") != "generate":
        return
    asset_ids = [row["id"] for row in binding["targets"] if row.get("kind") == "asset"]
    if len(asset_ids) != 1:
        raise ValidationError("Prepared proxy generation lacks one exact media target.")
    clip, _ = _clip_by_public_id(conn, project_id, asset_ids[0])
    if not any(
        callable(getattr(clip, method_name, None))
        for method_name in ("GenerateProxyMedia", "GenerateOptimizedMedia")
    ):
        raise APICallFailed("DaVinci Resolve does not expose media proxy generation.")


def _impact_target(target: Mapping[str, Any], revisions: Mapping[str, str]) -> dict[str, str]:
    target_id = target.get("id")
    private_kind = target.get("kind")
    if not isinstance(target_id, str) or target_id not in revisions:
        raise ValidationError("Prepared Media impact target lacks an exact revision.")
    if private_kind == "timeline":
        public_kind = "timeline"
    elif private_kind in {"asset", "folder", "artifact"}:
        public_kind = "media"
    else:
        raise ValidationError("Prepared Media impact target has an unsupported kind.")
    return {"kind": public_kind, "stableId": target_id, "revision": revisions[target_id]}


def _command_binding(action_id: str) -> tuple[str, str, str]:
    command_id = action_id.removeprefix("cutagent.action.")
    command = next((row for row in get_command_catalog() if row.command_id == command_id), None)
    function_name = _PRIVATE_MEDIA_HANDLER_FUNCTIONS.get(command_id)
    if command is None or function_name is None or command.path.split()[0] != "media" or (
        command.function_name and command.function_name != function_name
    ):
        raise RuntimeError(f"Media action lacks an authoritative handler: {action_id}")
    return command_id, "cutagent_cli.commands.media", function_name


class MediaExecutionAuthority:
    """The sole in-process authority admitted for the fixed Media handler table."""

    def __init__(self) -> None:
        # Production host composition happens before the private host reads a
        # request. Freeze every binding here so the compiled-runtime EOF smoke
        # exercises the real redacted catalog and fails before signing.
        bindings: dict[str, tuple[str, str, str]] = {}
        for action_id in MEDIA_RESIDUAL_CALLABLE_ACTION_IDS:
            binding = _command_binding(action_id)
            _command_id, module_name, function_name = binding
            if not callable(getattr(importlib.import_module(module_name), function_name, None)):
                raise RuntimeError(
                    f"Media action lacks a compiled authoritative handler: {action_id}"
                )
            bindings[action_id] = binding
        self._bindings = MappingProxyType(bindings)

    def _matches_carrier_admission(self, action_id: str, command_id: str, admitted_handler: object) -> bool:
        if action_id not in MEDIA_RESIDUAL_CALLABLE_ACTION_IDS:
            return False
        expected_command, module_name, function_name = self._bindings[action_id]
        function = inspect.unwrap(getattr(importlib.import_module(module_name), function_name, None))
        return expected_command == command_id and function is admitted_handler

    def invoke(self, action_id: str, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        if context.get("executionAuthority") is not self:
            raise ValidationError("Media handler execution lacks carrier admission authority.")
        command_id, module_name, function_name = self._bindings[action_id]
        wrapped = getattr(importlib.import_module(module_name), function_name, None)
        if not callable(wrapped):
            raise APICallFailed("The authoritative Media handler is unavailable.")
        function = inspect.unwrap(wrapped)
        try:
            value = _handler_input(action_id, prepared["lowering"]["handlerInput"])
            kwargs = _handler_kwargs(command_id, function, value)
        except Exception as failure:
            _tag_execution_failure(failure, "media.handler_lowering")
            raise
        with ExitStack() as stack:
            captured = stack.enter_context(capture_prepared_action_output())
            try:
                stack.enter_context(_prepared_action_admission_scope(action_id, command_id, self, function, context))
            except Exception as failure:
                _tag_execution_failure(failure, "media.handler_admission")
                raise
            try:
                returned = function(**kwargs)
            except Exception as failure:
                if not hasattr(failure, "prepared_action_substage"):
                    _tag_execution_failure(failure, "media.handler_invocation")
                raise
        if len(captured) > 1:
            raise ValidationError("Authoritative Media handler emitted multiple results.")
        if captured:
            return captured[0]
        if returned is not None:
            return returned
        raise ValidationError("Authoritative Media handler emitted no inspectable result.")

    def invoke_admitted_handler(
        self,
        action_id: str,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        handler_input: Mapping[str, Any],
    ) -> Any:
        """Satisfy the carrier authority contract without adding a second path."""

        if handler_input != prepared.get("lowering", {}).get("handlerInput"):
            raise ValidationError("Prepared Media handler input drifted from carrier custody.")
        return self.invoke(action_id, context, prepared)


def _artifact_state(binding: Mapping[str, Any], *, after: bool) -> dict[str, Any]:
    rows = {}
    for name, artifact in binding.get("artifacts", {}).items():
        path = Path(artifact["resolvedPath"])
        if path.is_symlink():
            raise ValidationError("Prepared Media artifact changed into a symlink.")
        if name == "output":
            identity = artifact.get("reservationIdentity")
            parent_identity = artifact.get("reservationParentIdentity")
            parent_stat = path.parent.lstat()
            if (path.parent.is_symlink() or not isinstance(parent_identity, Mapping)
                    or parent_stat.st_dev != parent_identity.get("device") or parent_stat.st_ino != parent_identity.get("inode")):
                raise ValidationError("Prepared Media output reservation parent changed.")
            if not path.is_file():
                if not after:
                    raise ValidationError("Prepared Media output reservation disappeared.")
                rows[name] = {"status": "absent"}
            else:
                stat = path.lstat()
                if not after and (not isinstance(identity, Mapping) or stat.st_dev != identity.get("device") or stat.st_ino != identity.get("inode") or stat.st_size != 0):
                    raise ValidationError("Prepared Media output reservation identity changed.")
                payload = path.read_bytes()
                rows[name] = {"byteCount": len(payload), "digest": _digest(payload.hex())}
        else:
            if not path.exists():
                raise ValidationError("Prepared Media input artifact disappeared.")
            if path.is_file():
                digest = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
                rows[name] = {"digest": digest}
            elif path.is_dir():
                digest_builder = hashlib.sha256()
                for child in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
                    if child.is_symlink():
                        raise ValidationError("Prepared Media input tree contains a symlink.")
                    relative = child.relative_to(path).as_posix().encode()
                    frame = (b"d" if child.is_dir() else b"f") + len(relative).to_bytes(8, "big") + relative
                    if child.is_dir():
                        digest_builder.update(frame)
                    elif child.is_file():
                        digest_builder.update(frame)
                        digest_builder.update(hashlib.sha256(child.read_bytes()).digest())
                    else:
                        raise ValidationError("Prepared Media input tree contains an unsupported entry.")
                digest = f"sha256:{digest_builder.hexdigest()}"
                rows[name] = {"directory": True, "digest": digest}
            else:
                raise ValidationError("Prepared Media input is not a file or directory.")
            if digest != artifact.get("contentDigest"):
                raise ValidationError("Prepared Media input content changed after carrier capture.")
    return rows


def _release_output_reservation(binding: Mapping[str, Any]) -> None:
    artifact = binding.get("artifacts", {}).get("output")
    if not isinstance(artifact, Mapping):
        return
    # Revalidate the exact zero-byte reservation at the last in-process point,
    # then release only that inode so native exporters that require a fresh path
    # can create the result inside the still-bound private directory.
    _artifact_state({"artifacts": {"output": artifact}}, after=False)
    path = Path(artifact["resolvedPath"])
    path.unlink()
    if path.exists() or path.is_symlink():
        raise ValidationError("Prepared Media output reservation could not be released safely.")


def _assert_current_folder_binding(
    action_id: str, value: Mapping[str, Any], binding: Mapping[str, Any], state: Mapping[str, Any]
) -> None:
    uses_implicit_current_folder = action_id in {
        "cutagent.action.media.folder.import_drb", "cutagent.action.media.duplicate",
    } or (
        action_id == "cutagent.action.media.clear_transcription"
        and not value.get("clip") and not value.get("folder")
    )
    if not uses_implicit_current_folder:
        return
    folder_ids = [row["id"] for row in binding["targets"] if row.get("kind") == "folder"]
    if len(folder_ids) != 1 or state.get("currentFolderId") != folder_ids[0]:
        raise ValidationError("Prepared Media current-folder target changed before execution.")


def _bound_folder_for_path(binding: Mapping[str, Any], raw_path: str) -> Mapping[str, Any] | None:
    folders = [row for row in binding.get("targets", []) if row.get("kind") == "folder"]
    roots = {str(row.get("path", "")).split("/", 1)[0] for row in folders if row.get("path")}
    if len(roots) != 1:
        return None
    root = next(iter(roots))
    logical = "/".join(part for part in str(raw_path).split("/") if part)
    full = logical if logical == root or logical.startswith(f"{root}/") else f"{root}/{logical}"
    matches = [row for row in folders if row.get("path") == full]
    return matches[0] if len(matches) == 1 else None


def _protected(
    state: Mapping[str, Any], target_ids: set[str], action_id: str,
    *, baseline_asset_ids: set[str] | None = None, baseline_folder_ids: set[str] | None = None,
    baseline_timeline_ids: set[str] | None = None, masked_folder_clip_count_ids: set[str] | None = None,
    masked_folder_subfolder_count_ids: set[str] | None = None,
) -> dict[str, Any]:
    allowed_asset_fields = {
        "cutagent.action.media.color.clear": {"properties"},
        "cutagent.action.media.color.set": {"properties"},
        "cutagent.action.media.flag.add": {"flags"},
        "cutagent.action.media.flag.clear": {"flags"},
        "cutagent.action.media.mark.clear": {"marks"},
        "cutagent.action.media.mark.set": {"marks"},
        "cutagent.action.media.marker.add": {"markers"},
        "cutagent.action.media.marker.delete": {"markers"},
        "cutagent.action.media.matte.delete": {"mattes"},
        "cutagent.action.media.move": {"folder", "folderId"},
        "cutagent.action.media.folders.move": {"folder", "folderId"},
        "cutagent.action.media.rename": {"name", "properties"},
        "cutagent.action.media.proxy": {"properties"},
        "cutagent.action.media.proxy.link_fullres": {"properties"},
        "cutagent.action.media.relink": {"properties"},
        "cutagent.action.media.replace": {"metadata", "properties"},
        "cutagent.action.media.replace_preserve_subclip": {"metadata", "properties"},
        "cutagent.action.media.sync_audio": {"audioMapping"},
        "cutagent.action.media.transcribe": {"properties"},
        "cutagent.action.media.clear_transcription": {"properties"},
        "cutagent.action.media.unlink": {"properties"},
    }.get(action_id, set())
    protected_assets = []
    for row in state["assets"]:
        if baseline_asset_ids is not None and row["id"] not in baseline_asset_ids:
            continue
        if row["id"] not in target_ids:
            protected_assets.append(deepcopy(row))
        elif action_id == "cutagent.action.media.stereo_create":
            continue
        elif action_id == "cutagent.action.media.create_timeline":
            # Native source usage increases with the verified new occurrences.
            # Its exact delta is checked separately; other properties stay protected.
            protected_assets.append({
                **deepcopy(row),
                "properties": {key: deepcopy(value) for key, value in row["properties"].items() if key != "Usage"},
            })
        elif action_id != "cutagent.action.media.delete":
            protected_assets.append({key: deepcopy(value) for key, value in row.items() if key not in allowed_asset_fields})
    folder_mutation = action_id in {
        "cutagent.action.media.folder.import_drb", "cutagent.action.media.folders.move",
    }
    return {
        "folders": sorted(
            ({key: deepcopy(item) for key, item in row.items()
              if (key != "clipCount" or row["id"] not in (masked_folder_clip_count_ids or set()))
              and (key != "subfolderCount" or row["id"] not in (masked_folder_subfolder_count_ids or set()))}
             for row in state["folders"]
             if (baseline_folder_ids is None or row["id"] in baseline_folder_ids)
             and not (folder_mutation and row["id"] in target_ids)),
            key=lambda row: row["id"],
        ),
        "assets": protected_assets,
        "timelines": sorted(
            (deepcopy(row) for row in state.get("timelines", [])
             if baseline_timeline_ids is None or row["id"] in baseline_timeline_ids),
            key=lambda row: row["id"],
        ),
        **({} if action_id in {
            "cutagent.action.media.create_timeline",
            "cutagent.action.media.selected.set",
        } else {"selectedIds": deepcopy(state.get("selectedIds", []))}),
        **({} if action_id in {"cutagent.action.media.folders.open", "cutagent.action.media.folders.root"} else {"currentFolderId": state.get("currentFolderId")}),
        **({} if action_id in {"cutagent.action.media.create_timeline", "cutagent.action.media.folder.import_drb"} else {"currentTimelineId": state.get("currentTimelineId")}),
    }


@dataclass(frozen=True)
class ResidualMediaMutationDescriptor:
    action_id: str
    operation_class = "mutation"
    version = 1

    @property
    def capability_id(self) -> str | None:
        return PREPARED_ACTION_ACTION_METADATA[self.action_id]["capabilityId"]

    def validate_input(self, value: Any) -> dict[str, Any]:
        if self.action_id == "cutagent.action.media.relink" and isinstance(value, Mapping) and "assetId" in value:
            required = {"projectId", "precondition", "assetId", "path"}
            if set(value) != required or any(not isinstance(value.get(key), str) or not value[key] for key in required):
                raise ValidationError("Prepared semantic Media relink input is malformed.")
            return _canonical(value)
        if self.action_id == "cutagent.action.media.sync_audio" and isinstance(value, Mapping) and "videoAssetId" in value:
            required = {"projectId", "precondition", "videoAssetId", "audioAssetIds", "method", "appendTracks"}
            audio_ids = value.get("audioAssetIds")
            if (set(value) != required or any(not isinstance(value.get(key), str) or not value[key] for key in required - {"audioAssetIds", "appendTracks"})
                    or not isinstance(audio_ids, list) or not audio_ids or any(not isinstance(item, str) or not item for item in audio_ids)
                    or len(set(audio_ids)) != len(audio_ids) or value.get("videoAssetId") in audio_ids
                    or value.get("method") not in {"waveform", "timecode"} or not isinstance(value.get("appendTracks"), bool)):
                raise ValidationError("Prepared semantic Media audio-sync input is malformed.")
            return _canonical(value)
        from ..sdk_action_descriptors.residual_av_prepared_action import _schema, _validate_schema
        normalized = _canonical(value)
        _validate_schema(normalized, _schema(self.action_id, "input"))
        return normalized

    def _current(self, context: Mapping[str, Any], binding: Mapping[str, Any]) -> dict[str, Any]:
        project, _ = _project_binding(context)
        conn = get_connection(require_project=True)
        native = _assert_native_project_binding(context, conn)
        state = _media_state(conn, project["projectId"])
        return {"native": native, "media": state, "artifacts": _artifact_state(binding, after=True)}

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        binding = _binding(context)
        project, _ = _project_binding(context)
        conn = get_connection(require_project=True)
        native = _assert_native_project_binding(context, conn)
        state = _media_state(conn, project["projectId"])
        if state["revision"] != binding["revision"]:
            raise ValidationError("Prepared Media Pool changed after carrier capture.")
        _assert_current_folder_binding(self.action_id, value, binding, state)
        for target in binding["targets"]:
            collection = state["assets"] if target["kind"] == "asset" else state["folders"] if target["kind"] == "folder" else None
            if collection is not None and sum(row["id"] == target["id"] for row in collection) != 1:
                raise ValidationError("Prepared Media target identity is missing or ambiguous in native readback.")
        if self.action_id == "cutagent.action.media.proxy":
            _assert_proxy_generation_capability(conn, project["projectId"], binding, value)
        exact = context.get("exactRequestBinding", {})
        target_ids = [row["id"] for row in binding["targets"]]
        exact_target_ids = exact.get("identities", {}).get("targetIds")
        if not isinstance(exact_target_ids, (list, tuple)) or list(exact_target_ids) != target_ids:
            raise ValidationError("Prepared Media target order drifted from carrier custody.")
        revisions = exact.get("revisions", {}).get("targets", {})

        def bound_revision(target_id: str) -> str:
            artifact = next(
                (row for row in binding["artifacts"].values() if row["stableId"] == target_id),
                None,
            )
            if artifact is not None:
                return artifact["revision"]
            target = next(row for row in binding["targets"] if row["id"] == target_id)
            return target.get("revision", binding["revision"])

        if any(revisions.get(target_id) != bound_revision(target_id) for target_id in target_ids):
            raise ValidationError("Prepared Media target revision drifted from carrier custody.")
        if self.action_id == "cutagent.action.media.create_timeline":
            output_targets = [row for row in binding["targets"] if row.get("kind") == "timeline"]
            if (
                len(output_targets) != 1
                or output_targets[0].get("name") != value["timelineName"]
                or output_targets[0].get("state") != "absent"
                or any(row.get("name") == value["timelineName"] for row in state["timelines"])
            ):
                raise ValidationError("Prepared Media timeline creation lacks one exact absent output target.")
        targets = [{"kind": "media_pool_target", "stableId": target_id, "revision": revisions[target_id]} for target_id in target_ids]
        impact_targets = [_impact_target(target, revisions) for target in binding["targets"]]
        impact = _impact(context, self.action_id, value)
        impact["effects"][0]["targets"] = impact_targets
        return {
            "targets": targets,
            "preState": {"native": native, "media": state, "artifacts": _artifact_state(binding, after=False)},
            "impact": impact,
            "lowering": {"input": deepcopy(dict(value)), "handlerInput": binding["handlerInput"], "binding": binding},
            "verification": {"minimumEvidence": ["readback", "structural"]},
            "recovery": {"strategy": (
                "restore_exact_media_name" if self.action_id == "cutagent.action.media.rename"
                else "manual_recovery_after_unproven_media_mutation"
            )},
        }

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        current = self._current(context, prepared["lowering"]["binding"])
        if current != prepared["preState"]:
            raise ValidationError("Prepared Media state changed before execution.")
        return {"targets": prepared["targets"], "preState": current}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        authority = context.get("executionAuthority")
        if not isinstance(authority, MediaExecutionAuthority):
            raise ValidationError("Prepared Media execution authority is unavailable.")
        try:
            current = self._current(context, prepared["lowering"]["binding"])
        except Exception as failure:
            _tag_execution_failure(failure, "media.second_current")
            raise
        if current != prepared["preState"]:
            failure = ValidationError("Prepared Media state changed at the execution boundary.")
            _tag_execution_failure(failure, "media.second_current_drift")
            raise failure
        try:
            _release_output_reservation(prepared["lowering"]["binding"])
        except Exception as failure:
            _tag_execution_failure(failure, "media.output_reservation_release")
            raise
        try:
            raw = authority.invoke(self.action_id, context, prepared)
        except Exception as failure:
            if not hasattr(failure, "prepared_action_substage"):
                _tag_execution_failure(failure, "media.handler_invocation")
            raise
        if self.action_id in {
            "cutagent.action.media.replace", "cutagent.action.media.replace_preserve_subclip",
        }:
            project, _ = _project_binding(context)
            target_id = next(row["stableId"] for row in prepared["targets"] if row["kind"] == "media_pool_target")
            clip, _ = _clip_by_public_id(get_connection(require_project=True), project["projectId"], target_id)
            prior = next(row for row in prepared["preState"]["media"]["assets"] if row["id"] == target_id)
            metadata_setter = getattr(clip, "SetMetadata", None)
            third_party_setter = getattr(clip, "SetThirdPartyMetadata", None)
            user_keys = set(_SEMANTIC_METADATA_NATIVE_KEYS.values()) - {"Clip Color"}
            if any(
                not callable(metadata_setter) or metadata_setter(key, item) is False
                for key, item in prior["metadata"].items() if key in user_keys
            ) or any(
                not callable(third_party_setter) or third_party_setter(key, item) is False
                for key, item in prior["thirdPartyMetadata"].items()
            ):
                raise APICallFailed("DaVinci Resolve replacement did not preserve user annotations.")
        try:
            after = self._current(context, prepared["lowering"]["binding"])
        except Exception as failure:
            _tag_execution_failure(failure, "media.after_current")
            raise
        return {"raw": raw, "after": after}

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        del context
        before = prepared["preState"]
        after = result["after"]
        binding = prepared["lowering"]["binding"]
        media_ids = {row["id"] for row in binding["targets"] if row["kind"] != "artifact"}
        baseline_asset_ids = {row["id"] for row in before["media"]["assets"]}
        baseline_folder_ids = {row["id"] for row in before["media"]["folders"]}
        baseline_timeline_ids = {row["id"] for row in before["media"]["timelines"]}
        assets_before = {row["id"]: row for row in before["media"]["assets"]}
        assets_after = {row["id"]: row for row in after["media"]["assets"]}
        folders_before = {row["id"]: row for row in before["media"]["folders"]}
        folders_after = {row["id"]: row for row in after["media"]["folders"]}
        asset_target_ids = [row["id"] for row in binding["targets"] if row["kind"] == "asset"]
        raw = result.get("raw")
        added_asset_rows = [
            row for row in after["media"]["assets"]
            if row["id"] not in baseline_asset_ids
        ]
        folder_count_deltas: dict[str, int] = {}
        subfolder_count_deltas: dict[str, int] = {}
        if (
            self.action_id == "cutagent.action.media.create_timeline"
            and len(added_asset_rows) == 1
            and isinstance(added_asset_rows[0].get("folderId"), str)
        ):
            folder_count_deltas[added_asset_rows[0]["folderId"]] = 1
        elif self.action_id == "cutagent.action.media.delete" and len(asset_target_ids) == 1:
            folder_count_deltas[assets_before[asset_target_ids[0]]["folderId"]] = -1
        elif self.action_id == "cutagent.action.media.duplicate" and len(asset_target_ids) == 1:
            destination_id = (before["media"].get("currentFolderId")
                              if isinstance(raw, Mapping) and raw.get("fallback_import") is True
                              else assets_before[asset_target_ids[0]]["folderId"])
            if destination_id:
                folder_count_deltas[destination_id] = 1
        elif self.action_id == "cutagent.action.media.stereo_create":
            if len(asset_target_ids) == 2:
                right_folder = assets_before[asset_target_ids[1]]["folderId"]
                folder_count_deltas[right_folder] = -1
        elif self.action_id == "cutagent.action.media.move" and len(asset_target_ids) == 1:
            source_id = assets_before[asset_target_ids[0]]["folderId"]
            destination = _bound_folder_for_path(binding, prepared["lowering"]["input"]["target"])
            if destination and destination["id"] != source_id:
                folder_count_deltas[source_id] = -1
                folder_count_deltas[destination["id"]] = 1
        elif self.action_id == "cutagent.action.media.folders.move":
            value = prepared["lowering"]["input"]
            source = _bound_folder_for_path(binding, value["path"])
            destination = _bound_folder_for_path(binding, value["targetPath"])
            if source and destination:
                source_path = folders_before[source["id"]]["path"]
                parent_path = source_path.rsplit("/", 1)[0]
                parent = next((row for row in folders_before.values() if row["path"] == parent_path), None)
                if parent and parent["id"] != destination["id"]:
                    subfolder_count_deltas[parent["id"]] = -1
                    subfolder_count_deltas[destination["id"]] = 1
        protected_before = _protected(
            before["media"], media_ids, self.action_id,
            masked_folder_clip_count_ids=set(folder_count_deltas),
            masked_folder_subfolder_count_ids=set(subfolder_count_deltas),
        )
        allows_asset_addition = self.action_id in {
            "cutagent.action.media.create_timeline",
            "cutagent.action.media.duplicate",
            "cutagent.action.media.folder.import_drb",
        }
        allows_folder_addition = self.action_id == "cutagent.action.media.folder.import_drb"
        protected_after = _protected(
            after["media"], media_ids, self.action_id,
            baseline_asset_ids=baseline_asset_ids if allows_asset_addition else None,
            baseline_folder_ids=baseline_folder_ids if allows_folder_addition else None,
            baseline_timeline_ids=baseline_timeline_ids if self.action_id in {"cutagent.action.media.create_timeline", "cutagent.action.media.folder.import_drb"} else None,
            masked_folder_clip_count_ids=set(folder_count_deltas),
            masked_folder_subfolder_count_ids=set(subfolder_count_deltas),
        )
        protected = before["native"] == after["native"] and protected_before == protected_after
        changed = before["media"] != after["media"]
        output = binding["artifacts"].get("output")
        output_proven = output is not None and after["artifacts"].get("output", {}).get("byteCount", 0) > 0
        value = prepared["lowering"]["input"]
        exact = False
        target_fields_preserved = True
        folder_counts_exact = all(
            folder_id in folders_before and folder_id in folders_after
            and folders_after[folder_id]["clipCount"] == folders_before[folder_id]["clipCount"] + delta
            for folder_id, delta in folder_count_deltas.items()
        )
        folder_counts_exact = folder_counts_exact and all(
            folder_id in folders_before and folder_id in folders_after
            and folders_after[folder_id]["subfolderCount"] == folders_before[folder_id]["subfolderCount"] + delta
            for folder_id, delta in subfolder_count_deltas.items()
        )

        def property_value(row: Mapping[str, Any] | None, *keys: str) -> Any:
            properties = row.get("properties", {}) if isinstance(row, Mapping) else {}
            for key in keys:
                matches = [item for name, item in properties.items() if str(name).casefold() == key.casefold()]
                if len(matches) == 1:
                    return matches[0]
            return None

        def same_path(actual: Any, expected: str) -> bool:
            if not isinstance(actual, str) or not actual:
                return False
            return Path(actual).resolve(strict=False) == Path(expected).resolve(strict=False)

        def without_keys(mapping: Any, keys: set[str]) -> Any:
            if not isinstance(mapping, Mapping):
                return mapping
            folded = {key.casefold() for key in keys}
            return {name: item for name, item in mapping.items() if str(name).casefold() not in folded}

        def target_maps_preserved(field: str, mutable_keys: set[str]) -> bool:
            return all(
                target_id in assets_before and target_id in assets_after
                and without_keys(assets_before[target_id].get(field), mutable_keys)
                == without_keys(assets_after[target_id].get(field), mutable_keys)
                for target_id in asset_target_ids
            )

        def casefold_mapping_value(mapping: Any, key: str) -> Any:
            if not isinstance(mapping, Mapping):
                return None
            matches = [item for name, item in mapping.items() if str(name).casefold() == key.casefold()]
            return matches[0] if len(matches) == 1 else None

        source_property_keys = {
            "File Path", "FilePath", "Source File", "SourcePath", "File Name",
            "Clip Name", "Type", "Video Codec", "Audio Codec", "Resolution",
            "FPS", "Frame Rate", "Duration", "Start TC", "Start Timecode",
            "Proxy Media Path", "Proxy Path", "Optimized Media Path",
        }

        if self.action_id == "cutagent.action.media.rename":
            target_id = next(row["id"] for row in binding["targets"] if row["kind"] == "asset")
            target = assets_after.get(target_id)
            exact = bool(target and target["name"] == value["new"] and property_value(target, "Clip Name") == value["new"])
            target_fields_preserved = target_maps_preserved("properties", {"Clip Name"})
        elif self.action_id == "cutagent.action.media.delete":
            target_id = next(row["id"] for row in binding["targets"] if row["kind"] == "asset")
            exact = all(row["id"] != target_id for row in after["media"]["assets"])
        elif self.action_id == "cutagent.action.media.selected.set":
            target_id = next(row["id"] for row in binding["targets"] if row["kind"] == "asset")
            exact = after["media"]["selectedIds"] == [target_id]
        elif self.action_id in {"cutagent.action.media.folders.open", "cutagent.action.media.folders.root"}:
            target_id = next(row["id"] for row in binding["targets"] if row["kind"] == "folder")
            exact = after["media"]["currentFolderId"] == target_id
        elif self.action_id == "cutagent.action.media.create_timeline":
            added = [row for row in after["media"]["timelines"] if row["id"] not in {item["id"] for item in before["media"]["timelines"]}]
            ids_by_name = {row["name"]: row["id"] for row in binding["targets"] if row["kind"] == "asset"}
            expected_ids = [ids_by_name.get(name) for name in value["clips"]]
            created_asset = added_asset_rows[0] if len(added_asset_rows) == 1 else None
            expected_occurrences = Counter(expected_ids)
            usage_counts = added[0].get("mediaPoolItemUsageCounts") if len(added) == 1 else None
            if (not isinstance(usage_counts, Mapping)
                    or set(usage_counts) != set(expected_ids)
                    or any(not isinstance(count, int) or isinstance(count, bool)
                           or count < expected_occurrences[asset_id]
                           for asset_id, count in usage_counts.items())):
                target_fields_preserved = False
                usage_counts = {}
            for asset_id, count in usage_counts.items():
                prior_usage = assets_before.get(asset_id, {}).get("properties", {}).get("Usage")
                current_usage = assets_after.get(asset_id, {}).get("properties", {}).get("Usage")
                if prior_usage is None and current_usage is None:
                    continue
                if (not isinstance(prior_usage, str) or not prior_usage.isdecimal()
                        or not isinstance(current_usage, str) or not current_usage.isdecimal()
                        or int(current_usage) != int(prior_usage) + count):
                    target_fields_preserved = False
            exact = bool(len(added) == 1 and created_asset and all(expected_ids)
                         and added[0]["name"] == value["timelineName"]
                         and added[0].get("mediaPoolItemIds") == expected_ids
                         and after["media"].get("currentTimelineId") == added[0]["id"]
                         and created_asset.get("id") != added[0]["id"]
                         and created_asset.get("name") == value["timelineName"]
                         and created_asset.get("folderId") == before["media"].get("currentFolderId")
                         and "timeline" in str(property_value(created_asset, "Type") or "").casefold()
                         and after["media"].get("selectedIds") == [created_asset["id"]])
        elif self.action_id == "cutagent.action.media.duplicate":
            added = [row for row in after["media"]["assets"] if row["id"] not in baseline_asset_ids]
            source = assets_before.get(asset_target_ids[0]) if len(asset_target_ids) == 1 else None
            source_path = property_value(source, "File Path", "Source File", "SourcePath")
            duplicate_path = property_value(added[0], "File Path", "Source File", "SourcePath") if len(added) == 1 else None
            expected_folder = (before["media"].get("currentFolderId")
                               if isinstance(raw, Mapping) and raw.get("fallback_import") is True
                               else source.get("folderId") if source else None)
            exact = bool(len(added) == 1 and source is not None and isinstance(source_path, str)
                         and added[0]["folderId"] == expected_folder
                         and same_path(duplicate_path, source_path)
                         and (value.get("newName") is None or added[0]["name"] == value["newName"])
                         and isinstance(raw, Mapping) and raw.get("duplicate"))
        elif self.action_id == "cutagent.action.media.stereo_create":
            added = [row for row in after["media"]["assets"] if row["id"] not in baseline_asset_ids]
            left = assets_before.get(asset_target_ids[0]) if len(asset_target_ids) == 2 else None
            right_id = asset_target_ids[1] if len(asset_target_ids) == 2 else None
            surviving = assets_after.get(asset_target_ids[0]) if len(asset_target_ids) == 2 else None
            exact = bool(not added and left and surviving and right_id not in assets_after
                         and {key: item for key, item in left.items() if key != "properties"}
                         == {key: item for key, item in surviving.items() if key != "properties"}
                         and without_keys(left["properties"], {"Type"}) == without_keys(surviving["properties"], {"Type"})
                         and str(property_value(surviving, "Type") or "").casefold() == "stereo"
                         and isinstance(raw, Mapping) and raw.get("created") is True)
        elif self.action_id == "cutagent.action.media.folder.import_drb":
            current = next((row for row in binding["targets"] if row["kind"] == "folder"), None)
            added_assets = [row for row in after["media"]["assets"] if row["id"] not in baseline_asset_ids]
            added_folders = [row for row in after["media"]["folders"] if row["id"] not in baseline_folder_ids]
            added_timelines = [row for row in after["media"]["timelines"] if row["id"] not in baseline_timeline_ids]
            exact = bool(current and (added_assets or added_folders or added_timelines)
                         and all(row["folder"] == current["path"] or row["folder"].startswith(f"{current['path']}/") for row in added_assets)
                         and all(row["path"].startswith(f"{current['path']}/") for row in added_folders)
                         and after["media"].get("currentTimelineId") in {
                             before["media"].get("currentTimelineId"), *(row["id"] for row in added_timelines),
                         })
        elif self.action_id == "cutagent.action.media.folder.export_drb":
            exact = output_proven
        elif self.action_id == "cutagent.action.media.transcode":
            try:
                probe = subprocess.run(
                    [resolve_tool("ffprobe"), "-v", "error", "-show_entries", "format=format_name:stream=codec_name", "-of", "json", output["resolvedPath"]],
                    check=True, capture_output=True, text=True, timeout=30,
                )
                facts = json.loads(probe.stdout)
                formats = {item.casefold() for item in str(facts.get("format", {}).get("format_name", "")).split(",") if item}
                codecs = {str(item.get("codec_name", "")).casefold().replace(".", "") for item in facts.get("streams", [])}
                expected_format = str(value.get("format") or "").casefold().replace(".", "")
                expected_codec = str(value.get("codec") or "").casefold().replace(".", "")
                exact = bool(output_proven and formats and codecs
                             and (not expected_format or expected_format in {item.replace(".", "") for item in formats})
                             and (not expected_codec or expected_codec in codecs))
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
                exact = False
        elif self.action_id == "cutagent.action.media.metadata.export":
            try:
                blob = Path(output["resolvedPath"]).read_bytes() if output_proven else b""
                text = blob.decode("utf-16") if blob.startswith((b"\xff\xfe", b"\xfe\xff")) else blob.decode("utf-8-sig")
                rows = list(csv.DictReader(io.StringIO(text)))
                requested = asset_target_ids or sorted(baseline_asset_ids)
                expected_files = Counter(
                    Path(str(property_value(assets_before[target_id], "File Name", "File Path", "Source File") or "")).name
                    for target_id in requested
                )
                actual_files = Counter(str(row.get("File Name") or "") for row in rows)
                exact = bool(isinstance(raw, Mapping) and raw.get("exported") is True
                             and rows and len(rows) == len(requested)
                             and "File Name" in (rows[0].keys() if rows else ())
                             and all(actual_files[name] >= count for name, count in expected_files.items() if name))
            except (OSError, UnicodeError, csv.Error):
                exact = False
        elif self.action_id == "cutagent.action.media.extract_template":
            requested_fields = value.get("fields", ["text", "image"])
            exact = bool(isinstance(raw, Mapping) and not changed and all(
                isinstance(raw.get(field), Mapping) and raw[field].get("value") not in {None, ""}
                for field in requested_fields
            ))
        elif self.action_id in {"cutagent.action.media.color.set", "cutagent.action.media.color.clear"}:
            target = assets_after.get(asset_target_ids[0]) if len(asset_target_ids) == 1 else None
            observed = property_value(target, "Clip Color")
            expected_color = media_pool.normalize_clip_color(value["color"]) if self.action_id.endswith("set") else None
            exact = observed == expected_color if self.action_id.endswith("set") else observed in {None, ""}
            target_fields_preserved = target_maps_preserved("properties", {"Clip Color"})
        elif self.action_id in {"cutagent.action.media.flag.add", "cutagent.action.media.flag.clear"}:
            before_flags = assets_before.get(asset_target_ids[0], {}).get("flags") if len(asset_target_ids) == 1 else None
            flags = assets_after.get(asset_target_ids[0], {}).get("flags") if len(asset_target_ids) == 1 else None
            color = media_pool.normalize_flag_color(value["color"]) if value.get("color") else None
            if isinstance(before_flags, list) and isinstance(flags, list):
                expected_flags = set(before_flags) | {color} if self.action_id.endswith("add") else (set(before_flags) - {color} if color else set())
                exact = set(flags) == expected_flags and len(flags) == len(set(flags))
        elif self.action_id in {"cutagent.action.media.mark.set", "cutagent.action.media.mark.clear"}:
            before_marks = assets_before.get(asset_target_ids[0], {}).get("marks") if len(asset_target_ids) == 1 else None
            marks = assets_after.get(asset_target_ids[0], {}).get("marks") if len(asset_target_ids) == 1 else None
            mark_type = value.get("markType", "all")
            mark = marks.get(mark_type) if isinstance(marks, Mapping) else None
            if mark_type == "all":
                mutable_types = {kind for kind in ("video", "audio") if isinstance(before_marks, Mapping) and kind in before_marks}
                if self.action_id.endswith("set"):
                    media_type = str(property_value(assets_before.get(asset_target_ids[0]), "Type") or "").casefold()
                    mutable_types |= {kind for kind in ("video", "audio") if kind in media_type}
            else:
                mutable_types = {mark_type}
            target_fields_preserved = without_keys(before_marks, mutable_types) == without_keys(marks, mutable_types)
            if self.action_id.endswith("set") and mark_type == "all":
                exact = bool(mutable_types and isinstance(raw, Mapping) and raw.get("success") is True
                             and isinstance(marks, Mapping) and all(
                    isinstance(marks.get(kind), Mapping)
                    and marks[kind].get("in") == value["markIn"] and marks[kind].get("out") == value["markOut"]
                    for kind in mutable_types
                ))
            elif self.action_id.endswith("set"):
                exact = bool(isinstance(raw, Mapping) and raw.get("success") is True
                             and isinstance(mark, Mapping) and mark.get("in") == value["markIn"] and mark.get("out") == value["markOut"])
            elif mark_type == "all":
                exact = bool(isinstance(raw, Mapping) and raw.get("cleared") is True
                             and isinstance(marks, Mapping) and all(kind not in marks for kind in mutable_types))
            else:
                exact = bool(isinstance(raw, Mapping) and raw.get("cleared") is True and isinstance(marks, Mapping) and mark is None)
        elif self.action_id in {"cutagent.action.media.marker.add", "cutagent.action.media.marker.delete"}:
            before_markers = assets_before.get(asset_target_ids[0], {}).get("markers") if len(asset_target_ids) == 1 else None
            markers = assets_after.get(asset_target_ids[0], {}).get("markers") if len(asset_target_ids) == 1 else None
            marker = markers.get(str(value.get("frame"))) if isinstance(markers, Mapping) and value.get("frame") is not None else None
            if self.action_id.endswith("add"):
                target_fields_preserved = without_keys(before_markers, {str(value["frame"])}) == without_keys(markers, {str(value["frame"])})
                exact = isinstance(marker, Mapping) and all(marker.get(key) == expected for key, expected in {
                    "color": value.get("color", "Blue"), "name": value.get("markerName", ""),
                    "note": value.get("note", ""), "duration": value.get("duration", 1),
                }.items())
            elif value.get("frame") is not None:
                target_fields_preserved = without_keys(before_markers, {str(value["frame"])}) == without_keys(markers, {str(value["frame"])})
                exact = marker is None
            elif value.get("color"):
                expected_markers = {key: item for key, item in before_markers.items() if not isinstance(item, Mapping) or item.get("color") != value["color"]} if isinstance(before_markers, Mapping) else None
                exact = isinstance(markers, Mapping) and markers == expected_markers
            else:
                exact = isinstance(markers, Mapping) and not markers
        elif self.action_id == "cutagent.action.media.move":
            destination = _bound_folder_for_path(binding, value["target"])
            target = assets_after.get(asset_target_ids[0]) if len(asset_target_ids) == 1 else None
            exact = bool(destination and target and target.get("folderId") == destination["id"])
        elif self.action_id == "cutagent.action.media.folders.move":
            source = _bound_folder_for_path(binding, value["path"])
            destination = _bound_folder_for_path(binding, value["targetPath"])
            moved = folders_after.get(source["id"]) if source else None
            if source and destination and moved:
                source_before_path = folders_before[source["id"]]["path"]
                source_after_path = f"{folders_before[destination['id']]['path']}/{source_before_path.rsplit('/', 1)[-1]}"
                subtree_folders = {row_id: row for row_id, row in folders_before.items() if row["path"] == source_before_path or row["path"].startswith(f"{source_before_path}/")}
                subtree_assets = {row_id: row for row_id, row in assets_before.items() if row["folder"] == source_before_path or row["folder"].startswith(f"{source_before_path}/")}
                exact = (
                    all(row_id in folders_after and folders_after[row_id]["path"] == source_after_path + row["path"][len(source_before_path):] for row_id, row in subtree_folders.items())
                    and all(row_id in assets_after and assets_after[row_id]["folder"] == source_after_path + row["folder"][len(source_before_path):] for row_id, row in subtree_assets.items())
                    and folders_after.get(destination["id"], {}).get("path") == folders_before.get(destination["id"], {}).get("path")
                )
        elif self.action_id in {"cutagent.action.media.relink", "cutagent.action.media.replace", "cutagent.action.media.replace_preserve_subclip", "cutagent.action.media.proxy.link_fullres"}:
            target = assets_after.get(asset_target_ids[0]) if len(asset_target_ids) == 1 else None
            requested_path = Path(binding["handlerInput"]["path"])
            expected_path = requested_path / Path(str(property_value(assets_before.get(asset_target_ids[0]), "File Path", "Source File", "SourcePath") or "")).name if self.action_id == "cutagent.action.media.relink" and requested_path.is_dir() else requested_path
            exact = same_path(property_value(target, "File Path", "Source File", "SourcePath"), str(expected_path))
            if (
                property_value(target, "Clip Directory") is not None
                or property_value(assets_before.get(asset_target_ids[0]), "Clip Directory") is not None
            ):
                exact = exact and same_path(property_value(target, "Clip Directory"), str(expected_path.parent))
            if self.action_id == "cutagent.action.media.replace_preserve_subclip" and target is not None:
                before_properties = assets_before[asset_target_ids[0]]["properties"]
                bounds = {key: item for key, item in before_properties.items() if "subclip" in key.casefold() or key.casefold() in {"in", "out"}}
                exact = exact and all(property_value(target, key) == item for key, item in bounds.items())
            target_fields_preserved = target_maps_preserved("properties", source_property_keys | {"Clip Directory"})
            if self.action_id in {"cutagent.action.media.replace", "cutagent.action.media.replace_preserve_subclip"}:
                user_keys = set(_SEMANTIC_METADATA_NATIVE_KEYS.values()) - {"Clip Color"}
                target_fields_preserved = target_fields_preserved and all(
                    casefold_mapping_value(assets_before[asset_target_ids[0]]["metadata"], key)
                    == casefold_mapping_value(target["metadata"], key)
                    for key in user_keys
                )
        elif self.action_id == "cutagent.action.media.unlink":
            target = assets_after.get(asset_target_ids[0]) if len(asset_target_ids) == 1 else None
            exact = property_value(target, "File Path", "Source File", "SourcePath") in {None, ""}
            target_fields_preserved = target_maps_preserved("properties", source_property_keys)
        elif self.action_id == "cutagent.action.media.proxy":
            target = assets_after.get(asset_target_ids[0]) if len(asset_target_ids) == 1 else None
            proxy_path = property_value(target, "Proxy Media Path", "Proxy Path")
            operation = value["operation"]
            lowered_handler_input = _handler_input(self.action_id, binding["handlerInput"])
            exact = same_path(proxy_path, lowered_handler_input.get("link")) if operation["kind"] == "link" else (
                proxy_path in {None, ""} if operation["kind"] == "unlink" else isinstance(proxy_path, str) and bool(proxy_path)
            )
            target_fields_preserved = target_maps_preserved("properties", source_property_keys | {"Proxy"})
        elif self.action_id == "cutagent.action.media.sync_audio":
            def mapping_strings(mapping: Any) -> list[str]:
                if isinstance(mapping, str):
                    try:
                        return mapping_strings(json.loads(mapping))
                    except json.JSONDecodeError:
                        return [mapping]
                if isinstance(mapping, Mapping):
                    return [item for child in mapping.values() for item in mapping_strings(child)]
                if isinstance(mapping, list):
                    return [item for child in mapping for item in mapping_strings(child)]
                return [str(mapping)] if mapping is not None else []

            def parsed_mapping(mapping: Any) -> Any:
                if isinstance(mapping, str):
                    try:
                        return json.loads(mapping)
                    except json.JSONDecodeError:
                        return None
                return mapping

            def embedded_channels(mapping: Any) -> int | None:
                mapping = parsed_mapping(mapping)
                if isinstance(mapping, Mapping):
                    for key, item in mapping.items():
                        folded = str(key).casefold()
                        if "embedded" in folded and "channel" in folded and isinstance(item, (int, float)):
                            return int(item)
                    for item in mapping.values():
                        if (found := embedded_channels(item)) is not None:
                            return found
                elif isinstance(mapping, list):
                    for item in mapping:
                        if (found := embedded_channels(item)) is not None:
                            return found
                return None

            video_id = asset_target_ids[0] if asset_target_ids else None
            before_mapping = assets_before.get(video_id, {}).get("audioMapping")
            after_mapping = assets_after.get(video_id, {}).get("audioMapping")
            after_strings = mapping_strings(after_mapping)
            audio_sources = [assets_before[target_id] for target_id in asset_target_ids[1:] if target_id in assets_before]
            linked = all(any(
                candidate and any(candidate.casefold() in observed.casefold() for observed in after_strings)
                for candidate in {
                    source["name"], Path(str(property_value(source, "File Path", "File Name", "Source File") or "")).name,
                    str(property_value(source, "File Path", "Source File") or ""),
                }
            ) for source in audio_sources)
            retain_requested = value.get("appendTracks", value.get("retainEmbeddedAudio"))
            if retain_requested is True:
                retained = all(item in after_strings for item in mapping_strings(before_mapping))
            elif retain_requested is False:
                after_embedded = embedded_channels(after_mapping)
                retained = after_embedded in {None, 0}
            else:
                retained = True
            exact = bool(isinstance(raw, Mapping) and raw.get("synced") is True and video_id
                         and audio_sources and before_mapping != after_mapping and linked and retained)
        elif self.action_id in {"cutagent.action.media.transcribe", "cutagent.action.media.clear_transcription"}:
            targets = [assets_after.get(target_id) for target_id in asset_target_ids]
            transcription = [(
                property_value(row, "Transcription"), property_value(row, "Transcription Status")
            ) for row in targets if row is not None]
            if self.action_id.endswith("transcribe"):
                exact = bool(transcription) and all(text not in {None, ""} and status not in {None, ""} for text, status in transcription)
            else:
                exact = bool(transcription) and all(text in {None, ""} and status in {None, ""} for text, status in transcription)
            target_fields_preserved = target_maps_preserved("properties", {"Transcription", "Transcription Status"})
        elif self.action_id == "cutagent.action.media.matte.delete":
            target = assets_after.get(asset_target_ids[0]) if len(asset_target_ids) == 1 else None
            before_target = assets_before.get(asset_target_ids[0]) if len(asset_target_ids) == 1 else None
            mattes = target.get("mattes") if target else None
            before_mattes = before_target.get("mattes") if before_target else None
            expected = {str(Path(item).resolve(strict=False)) for item in binding["handlerInput"]["paths"]}
            normalized_after = sorted(str(Path(item).resolve(strict=False)) for item in mattes) if isinstance(mattes, list) else None
            normalized_expected = sorted(
                str(Path(item).resolve(strict=False)) for item in before_mattes
                if str(Path(item).resolve(strict=False)) not in expected
            ) if isinstance(before_mattes, list) else None
            exact = normalized_after is not None and normalized_after == normalized_expected
        elif self.action_id == "cutagent.action.media.growing_file.monitor":
            # DaVinci Resolve exposes no monitoring-state getter. The native
            # boolean is the official API acknowledgement; protected readback
            # is tracked separately and does not claim a monitoring-state getter.
            exact = isinstance(raw, Mapping) and raw.get("monitoring") is True and not changed
        passed = bool(protected and exact and target_fields_preserved and folder_counts_exact)
        acknowledged = self.action_id == "cutagent.action.media.growing_file.monitor" \
            and isinstance(raw, Mapping) and raw.get("monitoring") is True
        result["changed"] = bool(changed or output_proven or acknowledged)
        evidence = [
            {"modality": "readback", "digest": _digest(after), "summary": "Independent Media Pool readback was captured."},
            {"modality": "structural", "digest": _digest(protected_after), "summary": "All unrelated Media Pool identities and fields were preserved."},
        ]
        if self.action_id == "cutagent.action.media.growing_file.monitor":
            evidence.append({
                "modality": "structural",
                "digest": _digest({"monitoringAcknowledged": acknowledged}),
                "summary": "Recorded the native monitoring acknowledgement separately from protected Media Pool readback.",
            })
        return {
            "outcome": "passed" if passed else "manual_review_required",
            "evidence": evidence,
            "protectedStatePreserved": protected if passed else False,
        }

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        if self.action_id not in {
            "cutagent.action.media.rename", "cutagent.action.media.replace",
            "cutagent.action.media.replace_preserve_subclip",
        }:
            try:
                exact = self._current(
                    context, prepared["lowering"]["binding"],
                ) == prepared["preState"]
            except Exception:
                exact = False
            return {
                "outcome": "succeeded" if exact else "manual_required",
                "attempted": True,
                "manualActionRequired": not exact,
            }
        try:
            project, _ = _project_binding(context)
            conn = get_connection(require_project=True)
            _assert_native_project_binding(context, conn)
            target_id = next(row["stableId"] for row in prepared["targets"] if row["kind"] == "media_pool_target")
            clip, _ = _clip_by_public_id(conn, project["projectId"], target_id)
            prior = next(row for row in prepared["preState"]["media"]["assets"] if row["id"] == target_id)
            if self.action_id in {"cutagent.action.media.replace", "cutagent.action.media.replace_preserve_subclip"}:
                method_name = "ReplaceClipPreserveSubClip" if self.action_id.endswith("replace_preserve_subclip") else "ReplaceClip"
                replacer = getattr(clip, method_name, None)
                old_path = next((item for key, item in prior["properties"].items() if key.casefold() in {"file path", "filepath", "source file", "sourcepath"}), None)
                restored = callable(replacer) and isinstance(old_path, str) and replacer(old_path) is not False
                metadata_setter = getattr(clip, "SetMetadata", None)
                third_party_setter = getattr(clip, "SetThirdPartyMetadata", None)
                user_keys = set(_SEMANTIC_METADATA_NATIVE_KEYS.values()) - {"Clip Color"}
                restored = restored and not any(
                    not callable(metadata_setter) or metadata_setter(key, item) is False
                    for key, item in prior["metadata"].items() if key in user_keys
                ) and not any(
                    not callable(third_party_setter) or third_party_setter(key, item) is False
                    for key, item in prior["thirdPartyMetadata"].items()
                )
                exact = restored and self._current(context, prepared["lowering"]["binding"]) == prepared["preState"]
                return {"outcome": "succeeded" if exact else "manual_required", "attempted": True, "manualActionRequired": not exact}
            old_name = prior["name"]
            setter = getattr(clip, "SetName", None)
            restored = callable(setter) and setter(old_name) is not False
            if not restored:
                property_setter = getattr(clip, "SetClipProperty", None)
                if callable(property_setter):
                    restored = any(property_setter(key, old_name) is not False for key in ("Clip Name", "Name"))
            exact = restored and self._current(context, prepared["lowering"]["binding"]) == prepared["preState"]
            return {"outcome": "succeeded" if exact else "manual_required", "attempted": True, "manualActionRequired": not exact}
        except Exception:
            return {"outcome": "manual_required", "attempted": True, "manualActionRequired": True}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        project, _ = _project_binding(context)
        ids = [row["stableId"] for row in prepared["targets"]]
        value = prepared["lowering"]["input"]
        after = result.get("after", {}).get("media", {})
        if self.action_id == "cutagent.action.media.relink" and "assetId" in value:
            asset = next(row for row in after["assets"] if row["id"] == value["assetId"])
            revision = after["revision"]
            return _assert_public({
                "projectId": project["projectId"],
                "asset": {"id": asset["id"], "snapshotId": _sdk_digest("snapshot_media_pool_item_", {"revision": revision, "stableId": asset["id"]}), "name": asset["name"]},
                "sourceFileName": Path(value["path"]).name,
                "revision": revision,
            })
        if self.action_id == "cutagent.action.media.sync_audio" and "videoAssetId" in value:
            return _assert_public({
                "projectId": project["projectId"], "videoAssetId": value["videoAssetId"],
                "audioAssetIds": value["audioAssetIds"], "syncedAsset": None,
                "revision": after["revision"],
            })
        if self.action_id == "cutagent.action.media.extract_template":
            raw = result["raw"]
            fields = []
            for field in value.get("fields", ["text", "image"]):
                extracted = raw[field]
                fields.append({
                    "field": field,
                    "textValue": str(extracted["value"]) if field == "text" else None,
                    "imageFileName": Path(str(extracted["value"])).name if field == "image" else None,
                    "source": str(extracted["source"]),
                    "property": str(extracted["property"]) if extracted.get("property") is not None else None,
                    "tool": str(extracted["tool"]) if extracted.get("tool") is not None else None,
                    "input": str(extracted["input"]) if extracted.get("input") is not None else None,
                })
            return _assert_public({
                "actionId": self.action_id,
                "applicability": _media_applicability(),
                "payload": {
                    "status": "no_op", "changed": False,
                    "data": {"outcome": "extract_template", "fields": fields, "attemptCount": len(raw.get("attempts", []))},
                    "verification": {"outcome": "passed", "evidence": [{"kind": "structural_readback", "summary": "Requested template fields were extracted without Media Pool mutation."}], "protectedState": "preserved"},
                },
            })
        if self.action_id == "cutagent.action.media.create_timeline":
            ids = [row["id"] for row in after["timelines"] if row["id"] not in {item["id"] for item in prepared["preState"]["media"]["timelines"]}]
        elif self.action_id == "cutagent.action.media.duplicate":
            ids = [row["id"] for row in after["assets"] if row["id"] not in {item["id"] for item in prepared["preState"]["media"]["assets"]}]
        elif self.action_id == "cutagent.action.media.folder.import_drb":
            prior = prepared["preState"]["media"]
            ids = [row["id"] for key in ("assets", "folders", "timelines") for row in after[key]
                   if row["id"] not in {item["id"] for item in prior[key]}]
        elif self.action_id == "cutagent.action.media.stereo_create":
            ids = [row["id"] for row in prepared["lowering"]["binding"]["targets"] if row["kind"] == "asset"]
        data = {"outcome": self.action_id.removeprefix("cutagent.action.media."), "targetIds": ids}
        if self.action_id == "cutagent.action.media.folder.import_drb":
            data = {**data, "targetIds": ids[:1024], "affectedCount": len(ids), "truncated": len(ids) > 1024}
        return _assert_public({
            "actionId": self.action_id,
            "applicability": _media_applicability(),
            "payload": {
                "status": "completed" if result["changed"] else "no_op", "changed": result["changed"],
                "data": data,
                "verification": {"outcome": "passed", "evidence": [{"kind": "structural_readback", "summary": "Exact targets and protected state matched independent readback."}], "protectedState": "preserved"},
            },
        })

    def validate_public_result(self, value: Any) -> bool:
        try:
            if self.action_id == "cutagent.action.media.relink" and isinstance(value, Mapping) and "asset" in value:
                return set(value) == {"projectId", "asset", "sourceFileName", "revision"}
            if self.action_id == "cutagent.action.media.sync_audio" and isinstance(value, Mapping) and "videoAssetId" in value:
                return set(value) == {"projectId", "videoAssetId", "audioAssetIds", "syncedAsset", "revision"}
            from ..sdk_action_descriptors.residual_av_prepared_action import _schema, _validate_schema
            _validate_schema(value, _schema(self.action_id, "result"))
            return value["payload"]["status"] in {"completed", "no_op"}
        except Exception:
            return False


def residual_media_prepared_action_descriptors() -> Mapping[str, ResidualMediaMutationDescriptor]:
    descriptors = {action_id: ResidualMediaMutationDescriptor(action_id) for action_id in MEDIA_RESIDUAL_CALLABLE_ACTION_IDS}
    if set(descriptors) != set(MEDIA_RESIDUAL_CALLABLE_ACTION_IDS) or len(descriptors) != 34:
        raise RuntimeError("Residual Media prepared-action contribution is incomplete.")
    return MappingProxyType(descriptors)


def residual_media_execution_authorities(authority: MediaExecutionAuthority) -> Mapping[str, MediaExecutionAuthority]:
    return MappingProxyType({action_id: authority for action_id in MEDIA_RESIDUAL_CALLABLE_ACTION_IDS})
