"""Project/Render/Storage/Media private action ownership decisions.

This packet delegates behavior already owned by accepted semantic SDK objects
and leaves every remaining low-level action unavailable. It does not create a
second mutation path around those reviewed object-model APIs.

Only :func:`project_render_storage_media_public_summary` may cross into the
source-readable Bridge, public SDK, generated knowledge, or release metadata.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, NoReturn

from .project_render_storage_media_prepared_action import (
    PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS,
)

class PrivateDescriptorUnavailable(ValueError):
    """The action has no complete safe private descriptor in this release."""

    def __init__(self, action_id: str, reason_code: str):
        super().__init__(f"{action_id} is unavailable: {reason_code}")
        self.action_id = action_id
        self.reason_code = reason_code


def _actions(prefix: str, suffixes: str) -> set[str]:
    return {f"cutagent.action.{prefix}.{suffix}" for suffix in suffixes.split()}


_PROJECT_UNSUPPORTED = {
    "cutagent.action.project.close": "active_project_close_has_no_dirty_state_readback_or_safe_compensation",
    "cutagent.action.project.folders.root": "project_manager_folder_path_has_no_stable_revision_identity",
    "cutagent.action.project.folders.up": "project_manager_folder_path_has_no_stable_revision_identity",
    "cutagent.action.project.save": "project_dirty_state_has_no_authoritative_native_readback",
    "cutagent.action.project.preset.load": "project_preset_load_has_no_complete_setting_delta_readback",
    "cutagent.action.project.preset.save": "created_project_preset_has_no_verified_delete_compensation",
    "cutagent.action.project.archive": "unmanaged_destination",
    "cutagent.action.project.cloud.create": "cloud_identity_not_safely_addressable",
    "cutagent.action.project.cloud.import": "unmanaged_source_and_cloud_identity",
    "cutagent.action.project.cloud.open": "cloud_identity_not_safely_addressable",
    "cutagent.action.project.cloud.restore": "unmanaged_source_and_cloud_identity",
    "cutagent.action.project.folders.create": "stable_project_folder_identity_missing",
    "cutagent.action.project.folders.delete": "destructive_target_not_safely_addressable",
    "cutagent.action.project.folders.open": "stable_project_folder_identity_missing",
    "cutagent.action.project.export": "carrier_managed_destination_contract_missing",
    "cutagent.action.project.import": "unmanaged_source",
    "cutagent.action.project.library.backup": "carrier_managed_destination_contract_missing",
    "cutagent.action.project.library.restore": "carrier_managed_source_contract_missing",
    "cutagent.action.project.library.create": "exact_public_identity_and_precondition_validation_missing",
    "cutagent.action.project.library.switch": "exact_public_identity_and_precondition_validation_missing",
    "cutagent.action.project.open": "durable_project_identity_cannot_be_rederived_in_private_runtime",
    "cutagent.action.project.delete": "durable_project_identity_cannot_be_rederived_in_private_runtime",
    "cutagent.action.project.cleanup_scratch": "durable_inactive_project_identity_missing",
    "cutagent.action.project.restore": "carrier_managed_source_contract_missing",
}


_RENDER_UNSUPPORTED = {
    **{
        action_id: "private_project_bound_bounded_result_handler_missing"
        for action_id in _actions(
            "render",
            "codecs formats job_status jobs mode.get presets quick_export_presets resolutions settings status",
        )
    },
    "cutagent.action.render.burnin.load": "burnin_preset_delta_has_no_complete_native_readback",
    "cutagent.action.render.preset_load": "stable_render_preset_identity_and_revision_missing",
    "cutagent.action.render.add": "superseded_by_managed_durable_render_export",
    "cutagent.action.render.cancel": "snapshot_job_identity_cannot_authorize_durable_operation_cancellation",
    "cutagent.action.render.delete": "destructive_queue_delete_has_no_native_restore_operation",
    "cutagent.action.render.stop": "snapshot_job_identity_cannot_authorize_durable_operation_cancellation",
    "cutagent.action.render.start": "private_long_running_job_artifact_reattachment_handler_missing",
    "cutagent.action.render.custom_range": "carrier_render_request_schema_has_no_range_contract",
    "cutagent.action.render.audio": "unmanaged_destination",
    "cutagent.action.render.burnin.export": "unmanaged_destination",
    "cutagent.action.render.burnin.import": "unmanaged_source",
    "cutagent.action.render.export_preset": "unmanaged_destination",
    "cutagent.action.render.import_preset": "unmanaged_source",
    "cutagent.action.render.preset_delete": "destructive_preset_recovery_unproven",
    "cutagent.action.render.quick_export": "unmanaged_destination",
    "cutagent.action.render.settings.replace": "authoritative_typed_input_contract_missing",
    "cutagent.action.render.settings_set": "authoritative_typed_input_contract_missing",
    "cutagent.action.render.settings.update": "authoritative_typed_input_contract_missing",
    "cutagent.action.render.archive_settings": "authoritative_typed_input_contract_missing",
    "cutagent.action.render.wait": "authoritative_long_running_result_contract_missing",
}

_STORAGE_UNSUPPORTED = {}

_RESIDUAL_UNSUPPORTED = {
    **_PROJECT_UNSUPPORTED,
    **_RENDER_UNSUPPORTED,
    **_STORAGE_UNSUPPORTED,
}
_RESIDUAL_SEMANTIC_EQUIVALENTS = {
    "cutagent.action.auto_edit.multicam": (
        "sdk.executeOperationBatch(client.workflows, sdk.defineOperationBatch(steps), options)"
    ),
    "cutagent.action.auto_edit.podcast_edit": (
        "sdk.executeOperationBatch(client.workflows, sdk.defineOperationBatch(steps), options)"
    ),
    "cutagent.action.auto_edit.podcast_multicam": (
        "sdk.executeOperationBatch(client.workflows, sdk.defineOperationBatch(steps), options)"
    ),
    "cutagent.action.auto_edit.run": (
        "sdk.executeOperationBatch(client.workflows, plan, options)"
    ),
    "cutagent.action.auto_edit.silence_cut": (
        "client.projects.current().then(project => project.timelines.current()).then(async timeline => "
        "timeline.managed.apply(await timeline.managed.preview(snapshot, program, options), applyOptions))"
    ),
    "cutagent.action.batch.run": (
        "sdk.executeOperationBatch(client.workflows, plan, options)"
    ),
    "cutagent.action.batch.validate": (
        "sdk.validateOperationBatch(plan)"
    ),
    "cutagent.action.bulk.clip_color_set": (
        "client.projects.current().then(project => project.timelines.current())"
        ".then(timeline => timeline.items.setColor(changes, options))"
    ),
    "cutagent.action.bulk.disable": (
        "client.projects.current().then(project => project.timelines.current())"
        ".then(timeline => timeline.items.disable(items, options))"
    ),
    "cutagent.action.bulk.enable": (
        "client.projects.current().then(project => project.timelines.current())"
        ".then(timeline => timeline.items.enable(items, options))"
    ),
    "cutagent.action.bulk.lut_set": (
        "sdk.applyColorLut(applications, lutOptions)"
    ),
    "cutagent.action.bulk.property_set": (
        "client.projects.current().then(project => project.timelines.current())"
        ".then(timeline => timeline.items.setProperties(items, options))"
    ),
    "cutagent.action.bulk.select": (
        "sdk.selectTimelineClips(snapshot, predicate, options)"
    ),
    "cutagent.action.render.codecs": (
        "const project = await client.projects.current(); "
        "await project.render.discovery(options)"
    ),
    "cutagent.action.render.formats": (
        "const project = await client.projects.current(); "
        "await project.render.discovery(options)"
    ),
    "cutagent.action.render.job_status": (
        "const project = await client.projects.current(); const page = await project.render.queue.list(options); "
        "await page.jobs[index].refreshStatus(options)"
    ),
    "cutagent.action.render.jobs": (
        "const project = await client.projects.current(); "
        "await project.render.queue.list(options)"
    ),
    "cutagent.action.render.mode.get": (
        "const project = await client.projects.current(); "
        "(await project.render.settings(options)).mode"
    ),
    "cutagent.action.render.presets": (
        "const project = await client.projects.current(); "
        "await project.render.presets(options)"
    ),
    "cutagent.action.render.resolutions": (
        "const project = await client.projects.current(); "
        "await project.render.discovery(options)"
    ),
    "cutagent.action.render.settings": (
        "const project = await client.projects.current(); "
        "await project.render.settings(options)"
    ),
    "cutagent.action.render.status": (
        "const project = await client.projects.current(); "
        "await project.render.queue.list(options)"
    ),
    "cutagent.action.render.quick_export_presets": (
        "await client.lowLevel.read('cutagent.action.render.quick_export_presets', input, options)"
    ),
    **{
        action_id: (
            f"await client.actions.{'read' if action_id.endswith(('.files', '.volumes')) else 'start'}"
            f"('{action_id}', input, options)"
        )
        for action_id in (
            "cutagent.action.storage.files",
            "cutagent.action.storage.import",
            "cutagent.action.storage.import_sequence",
            "cutagent.action.storage.import_subclip",
            "cutagent.action.storage.matte.add",
            "cutagent.action.storage.matte.timeline_add",
            "cutagent.action.storage.reveal",
            "cutagent.action.storage.volumes",
        )
    },
    "cutagent.action.render.add": (
        "client.projects.current().then(project => project.render.export(request, options))"
    ),
    "cutagent.action.render.start": (
        "client.projects.current().then(project => project.render.queue.start(jobs, options))"
    ),
    "cutagent.action.render.custom_range": (
        "client.projects.current().then(project => project.render.export({...request, range: {kind: 'custom', startFrame, endExclusiveFrame}}, options))"
    ),
    "cutagent.action.render.wait": (
        "client.projects.current().then(project => project.render.export(request, options)).then(operation => operation.wait())"
    ),
    "cutagent.action.render.cancel": (
        "client.operations.reattach(operationId, options).then(operation => operation.requestCancellation(options))"
    ),
    "cutagent.action.render.stop": (
        "client.operations.reattach(operationId, options).then(operation => operation.requestCancellation(options))"
    ),
    "cutagent.action.render.audio": (
        "client.projects.current().then(project => project.render.export({...request, settings: {...request.settings, exportVideo: false, exportAudio: true}}, options))"
    ),
    "cutagent.action.render.quick_export": (
        "client.projects.current().then(project => project.render.export(request, options))"
    ),
    "cutagent.action.render.export_file": (
        "client.projects.current().then(project => project.render.export(request, options)).then(operation => operation.wait()).then(terminal => terminal.status === 'succeeded' ? terminal.result.artifact.copyTo(destinationPath) : Promise.reject(terminal))"
    ),
    "cutagent.action.render.transcript_audio": (
        "client.projects.current().then(project => project.render.export({...request, settings: {...request.settings, exportVideo: false, exportAudio: true}}, options)).then(operation => operation.wait()).then(terminal => terminal.status === 'succeeded' ? terminal.result.artifact.copyTo(destinationPath) : Promise.reject(terminal))"
    ),
}
_RESIDUAL_UNSUPPORTED = {
    action_id: reason
    for action_id, reason in _RESIDUAL_UNSUPPORTED.items()
    if action_id not in _RESIDUAL_SEMANTIC_EQUIVALENTS
    and action_id not in PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS
}

_MEDIA_TYPED_UNSUPPORTED = _actions(
    "media",
    """append clear_transcription color.clear color.set create_timeline delete duplicate
    extract_template flag.add flag.clear folder.export_drb folder.import_drb folders.move folders.open
    folders.root growing_file.monitor mark.clear mark.set marker.add marker.delete matte.delete metadata.export
    move proxy proxy.link_fullres relink rename replace replace_preserve_subclip selected.set stereo_create
    sync_audio transcode transcribe unlink""",
)
_MEDIA_TYPED_UNSUPPORTED.update({
    "cutagent.action.media.folders.create",
    "cutagent.action.media.folders.delete",
    "cutagent.action.media.metadata",
    "cutagent.action.media.property_set",
    "cutagent.action.media.third_party_metadata.set",
})
_MEDIA_TYPED_UNSUPPORTED -= set(PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS)

_MEDIA_SEMANTIC_EQUIVALENTS = {
    "cutagent.action.media.append": (
        "client.projects.current().then(project => project.timelines.current())"
        ".then(timeline => timeline.edit.previewInsert(snapshot, asset, placement)"
        ".then(impact => timeline.edit.insert(impact, options)))"
    ),
}


def _unsupported_record(action_id: str, reason_code: str) -> dict[str, Any]:
    return {
        "actionId": action_id,
        "classification": "unsupported_not_advertised",
        "reasonCode": reason_code,
        "hasPrivateLowering": False,
    }


def _delegated_record(action_id: str, equivalent: str) -> dict[str, Any]:
    return {
        "actionId": action_id,
        "classification": "delegated_semantic_api",
        "highLevelEquivalent": equivalent.strip(),
        "advertisedByPrivatePacket": False,
        "hasPrivateLowering": False,
    }


def _callable_record(action_id: str) -> dict[str, Any]:
    return {
        "actionId": action_id,
        "classification": "callable_prepared_action",
        "actionContractVersion": 1,
        "hasPrivateLowering": True,
    }


def _media_record(action_id: str) -> dict[str, Any]:
    if action_id in _MEDIA_SEMANTIC_EQUIVALENTS:
        return {
            "actionId": action_id,
            "classification": "delegated_semantic_api",
            "highLevelEquivalent": _MEDIA_SEMANTIC_EQUIVALENTS[action_id].strip(),
            "advertisedByPrivatePacket": False,
            "hasPrivateLowering": False,
        }
    raw_path = any(
        action_id.endswith(f".{suffix}")
        for suffix in (
            "extract_template", "folder.export_drb", "folder.import_drb", "matte.delete",
            "metadata.export", "proxy", "proxy.link_fullres", "replace",
            "replace_preserve_subclip", "transcode",
        )
    )
    destructive = any(
        action_id.endswith(f".{suffix}")
        for suffix in ("delete", "folders.move", "matte.delete", "unlink")
    )
    reason = "unmanaged_source_or_destination" if raw_path else (
        "destructive_target_not_safely_addressable"
        if destructive
        else "stable_media_identity_or_verified_result_missing"
    )
    return _unsupported_record(action_id, reason)


def project_render_storage_media_descriptor_packet() -> dict[str, Any]:
    """Return complete private ownership decisions for this packet."""
    descriptors = sorted(
        (
            *(
                _callable_record(action_id)
                for action_id in PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS
            ),
            *(
                _delegated_record(action_id, equivalent)
                for action_id, equivalent in _RESIDUAL_SEMANTIC_EQUIVALENTS.items()
            ),
            *(
                _unsupported_record(action_id, reason)
                for action_id, reason in _RESIDUAL_UNSUPPORTED.items()
            ),
        ),
        key=lambda item: item["actionId"],
    )
    media_audit = sorted(
        (_media_record(action_id) for action_id in _MEDIA_TYPED_UNSUPPORTED),
        key=lambda item: item["actionId"],
    )
    media_unsupported = sum(item["classification"] == "unsupported_not_advertised" for item in media_audit)
    delegated = len(media_audit) - media_unsupported
    callable_descriptors = len(PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS)
    delegated_descriptors = len(_RESIDUAL_SEMANTIC_EQUIVALENTS)
    unsupported_descriptors = len(descriptors) - delegated_descriptors - callable_descriptors
    return {
        "schemaVersion": 1,
        "packetId": "project-render-storage-media-context-v1",
        "descriptors": descriptors,
        "mediaAudit": media_audit,
        "summary": {
            "descriptorActions": len(descriptors),
            "callableDescriptors": callable_descriptors,
            "unsupportedDescriptors": unsupported_descriptors,
            "delegatedDescriptors": delegated_descriptors,
            "auditedTypedUnsupportedMedia": len(media_audit),
            "callableMediaDescriptors": sum(
                action_id.startswith("cutagent.action.media.")
                for action_id in PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS
            ),
            "unsupportedMedia": media_unsupported,
            "delegatedMedia": delegated,
            "totalReviewed": len(descriptors) + len(media_audit),
            "totalCallable": callable_descriptors,
            "totalUnsupported": unsupported_descriptors + media_unsupported,
            "totalDelegated": delegated_descriptors + delegated,
        },
    }


def project_render_storage_media_public_summary() -> dict[str, Any]:
    """Return the public-safe action decisions and exact counts."""
    packet = project_render_storage_media_descriptor_packet()
    actions = [
        {
            "actionId": item["actionId"],
            "classification": item["classification"],
            **({"highLevelEquivalent": item["highLevelEquivalent"]} if "highLevelEquivalent" in item else {}),
        }
        for item in (*packet["descriptors"], *packet["mediaAudit"])
    ]
    actions.sort(key=lambda item: item["actionId"])
    return {
        "schemaVersion": packet["schemaVersion"],
        "packetId": packet["packetId"],
        "summary": deepcopy(packet["summary"]),
        "actions": actions,
    }


def _deny(action_id: str, reason: str) -> NoReturn:
    raise PrivateDescriptorUnavailable(action_id, reason)


def prepare_project_render_storage_media_action(
    action_id: str,
    input_value: dict[str, Any],
    identities: dict[str, Any],
) -> NoReturn:
    """Deny every raw action path owned or audited by this packet."""
    del input_value, identities
    if action_id in _RESIDUAL_SEMANTIC_EQUIVALENTS:
        _deny(action_id, "accepted_semantic_api_owns_execution")
    if action_id in PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS:
        _deny(action_id, "signed_prepared_action_carrier_owns_execution")
    if action_id in _RESIDUAL_UNSUPPORTED:
        _deny(action_id, _RESIDUAL_UNSUPPORTED[action_id])
    if action_id in _MEDIA_TYPED_UNSUPPORTED:
        decision = _media_record(action_id)
        _deny(action_id, decision.get("reasonCode", "accepted_semantic_api_owns_execution"))
    _deny(action_id, "descriptor_not_owned_by_packet")
