"""Fairlight track duplicate, folder, visibility, height, and format commands."""

from __future__ import annotations

def _track_duplicate_supported_subset_name(
    *,
    include_clips: bool,
    copy_volume: bool = False,
    copy_pan: bool = False,
    copy_clip_eq: bool = False,
    copy_clip_fx: bool = False,
    copy_color: bool = False,
) -> str:
    copied_parts: list[str] = []
    if copy_volume:
        copied_parts.append("volume")
    if copy_pan:
        copied_parts.append("pan")
    if copy_clip_eq and include_clips:
        copied_parts.append("clip_eq")
    if copy_clip_fx and include_clips:
        copied_parts.append("clip_fx")
    if copy_color:
        copied_parts.append("color")
    if copied_parts:
        prefix = "clips" if include_clips else "empty"
        return f"{prefix}_with_{'_'.join(copied_parts)}_no_other_processing"
    return "clips_no_processing" if include_clips else "empty_no_processing"


@track_app.command("duplicate")
@handle_errors
def track_duplicate(
    index: int = typer.Argument(..., min=1, help="Audio track index to duplicate"),
    include_clips: bool = typer.Option(True, "--include-clips/--empty", help="Whether the duplicate should include clips"),
    include_processing: bool = typer.Option(True, "--include-processing/--no-processing", help="Whether the duplicate should include mixer processing"),
    copy_volume: bool = typer.Option(False, "--copy-volume/--no-copy-volume", help="Copy the verified track Volume/fader subset via DB readback/writeback"),
    copy_pan: bool = typer.Option(False, "--copy-pan/--no-copy-pan", help="Copy the verified mono track Pan subset via DB readback/writeback"),
    copy_clip_eq: bool = typer.Option(False, "--copy-clip-eq/--no-copy-clip-eq", help="Copy verified clip-level EQ payloads for included clips via DB readback/writeback"),
    copy_clip_fx: bool = typer.Option(False, "--copy-clip-fx/--no-copy-clip-fx", help="Copy verified clip-level Fairlight FX payloads for included clips via DB readback/writeback"),
    copy_color: bool = typer.Option(False, "--copy-color/--no-copy-color", help="Copy the verified track color subset via DB readback/writeback"),
):
    """Duplicate a Fairlight audio track through the supported native no-processing subset."""
    if include_processing:
        unsupported_parts: list[str] = []
        required_native_api = ["duplicate an existing audio track"]
        if include_processing:
            unsupported_parts.append("processing")
            required_native_api.append("copy track processing/routing/sends/plugins to the duplicated track")
        requested = {
            "index": int(index),
            "include_clips": bool(include_clips),
            "include_processing": bool(include_processing),
            "copy_volume": bool(copy_volume),
            "copy_pan": bool(copy_pan),
            "copy_clip_eq": bool(copy_clip_eq),
            "copy_clip_fx": bool(copy_clip_fx),
            "copy_color": bool(copy_color),
            "unsupported_parts": unsupported_parts,
            "supported_subset_command": (
                f"cutagent fairlight track duplicate {int(index)} "
                f"{'--include-clips' if include_clips else '--empty'} --no-processing "
                f"{'--copy-volume ' if copy_volume else ''}"
                f"{'--copy-pan ' if copy_pan else ''}"
                f"{'--copy-clip-eq ' if copy_clip_eq else ''}"
                f"{'--copy-clip-fx ' if copy_clip_fx else ''}"
                f"{'--copy-color ' if copy_color else ''}--json"
            ),
        }
        _raise_fairlight_native_unavailable(
            capability_id="fairlight.track_duplicate",
            workflow="Full Fairlight track duplication",
            requested=requested,
            required_native_api=required_native_api,
            api_note=(
                "CutAgent CLI supports no-processing Fairlight track duplication through Timeline.AddTrack, "
                "track metadata readback, and media-pool backed clip append when --include-clips --no-processing "
                "is requested. Copying processing, routing, sends, inserts, and automation still lacks a "
                "verified native/API/DB model."
            ),
            workaround="Use the supported no-processing subset command, then use supported clip/mixer commands for safe explicit follow-up mutations.",
            extra_details=_FAIRLIGHT_TRACK_DUPLICATE_PARTIAL_BLOCKER_EVIDENCE,
        )

    enforce_mutation_policy("fairlight.track_duplicate", intended_engine="api_native", mutating=not is_dry_run())
    supported_subset = _track_duplicate_supported_subset_name(
        include_clips=bool(include_clips),
        copy_volume=bool(copy_volume),
        copy_pan=bool(copy_pan),
        copy_clip_eq=bool(copy_clip_eq),
        copy_clip_fx=bool(copy_clip_fx),
        copy_color=bool(copy_color),
    )
    native_api = [
        "Timeline.GetTrackSubType('audio', index)",
        'Timeline.AddTrack("audio", {"audioType": track_type, "index": index})',
        "Timeline.SetTrackName('audio', index, name)",
        "Timeline.SetTrackEnable('audio', index, enabled)",
        "Timeline.SetTrackLock('audio', index, locked)",
        "Timeline.GetItemListInTrack('audio', index)",
    ]
    if include_clips:
        native_api.extend(
            [
                "TimelineItem.GetMediaPoolItem()",
                "TimelineItem.GetLeftOffset()",
                "MediaPool.AppendToTimeline([{mediaPoolItem, trackIndex, trackType, mediaType, recordFrame, startFrame, endFrame}])",
            ]
        )
    if copy_volume:
        native_api.extend(
            [
                "Disk Project.db readback of source FLStudioModelBA fader lanes",
                "Disk Project.db mutation of target FLStudioModelBA fader lanes",
            ]
        )
    if copy_pan:
        native_api.extend(
            [
                "Disk Project.db readback of source FLStudioModelBA mono pan lane",
                "Disk Project.db mutation of target FLStudioModelBA mono pan lane",
            ]
        )
    if copy_clip_eq:
        native_api.extend(
            [
                "Disk Project.db readback of source Sm2TiItem.EffectFiltersBA clip EQ payloads",
                "Disk Project.db mutation of target Sm2TiItem.EffectFiltersBA clip EQ payloads",
            ]
        )
    if copy_clip_fx:
        native_api.extend(
            [
                "Disk Project.db readback of source Sm2TiItem.FieldsBlob FL::ClipFX payloads",
                "Disk Project.db mutation of target Sm2TiItem.FieldsBlob FL::ClipFX payloads",
            ]
        )
    if copy_color:
        native_api.extend(
            [
                "Disk Project.db readback of source Sm2TiTrack.FieldsBlob.Color",
                "Disk Project.db mutation of target Sm2TiTrack.FieldsBlob.Color through verified track color route",
            ]
        )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.track.duplicate",
                target={"kind": "audio_track", "track_type": "audio", "index": int(index)},
                changed=False,
                dry_run=True,
                include_clips=bool(include_clips),
                include_processing=False,
                copy_volume=bool(copy_volume),
                copy_pan=bool(copy_pan),
                copy_clip_eq=bool(copy_clip_eq),
                copy_clip_fx=bool(copy_clip_fx),
                copy_color=bool(copy_color),
                supported_subset=supported_subset,
                route="api_native+db_workaround" if (copy_volume or copy_pan or copy_clip_eq or copy_clip_fx or copy_color) else "api_native",
                native_api=native_api,
                verification_status="not_requested",
                preflight_command="cutagent fairlight tracks --json",
            ),
            title="Fairlight Track Duplicate Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    data = fairlight_ops.duplicate_empty_audio_track(
        conn,
        index=index,
        include_clips=bool(include_clips),
        copy_volume=bool(copy_volume),
        copy_pan=bool(copy_pan),
        copy_clip_eq=bool(copy_clip_eq),
        copy_clip_fx=bool(copy_clip_fx),
        copy_color=bool(copy_color),
    )
    output(
        mutation_payload(
            action="fairlight.track.duplicate",
            target={"kind": "audio_track", "track_type": "audio", "index": int(index)},
            changed=bool(data.get("changed")),
            runtime_write_called=True,
            include_clips=bool(data.get("include_clips")),
            include_processing=False,
            copy_volume=bool(data.get("copy_volume")),
            copy_pan=bool(data.get("copy_pan")),
            copy_clip_eq=bool(data.get("copy_clip_eq")),
            copy_clip_fx=bool(data.get("copy_clip_fx")),
            copy_color=bool(data.get("copy_color")),
            supported_subset=data.get("supported_subset"),
            route="api_native+db_workaround"
            if (data.get("copy_volume") or data.get("copy_pan") or data.get("copy_clip_eq") or data.get("copy_clip_fx") or data.get("copy_color"))
            else data.get("route"),
            source_track=data.get("source_track"),
            duplicated_track=data.get("duplicated_track"),
            clip_copy=data.get("clip_copy"),
            clip_eq_copy=data.get("clip_eq_copy"),
            clip_fx_copy=data.get("clip_fx_copy"),
            volume_copy=data.get("volume_copy"),
            pan_copy=data.get("pan_copy"),
            color_copy=data.get("color_copy"),
            native_api=data.get("native_api"),
            audio_tracks_before=data.get("audio_tracks_before"),
            audio_tracks_after=data.get("audio_tracks_after"),
            inserted_after_source=data.get("inserted_after_source"),
            verification=data.get("verification"),
            verification_status=(data.get("verification") or {}).get("status"),
            message="Duplicated Fairlight audio track without processing.",
        ),
        title="Fairlight Track Duplicate",
    )


_FAIRLIGHT_TRACK_VISIBILITY_BLOCKER_EVIDENCE = {
    "native_probe_evidence": {
        "runtime": "DaVinci Resolve 20 Free",
        "candidate_methods": [
            "Timeline.GetTrackVisible('audio', index)",
            "Timeline.GetTrackVisibility('audio', index)",
            "Timeline.GetIsTrackVisible('audio', index)",
            "Timeline.GetIsTrackHidden('audio', index)",
            "Timeline.SetTrackVisible('audio', index, visible)",
            "Timeline.SetTrackVisibility('audio', index, visible)",
            "Timeline.SetTrackHidden('audio', index, hidden)",
            "Timeline.ShowTrack('audio', index)",
        ],
        "probe_result": "method not available",
        "visibility_read_supported": False,
        "visibility_write_supported": False,
        "set_supported": False,
        "resolve_21_embedded_recheck": {
            "runtime": "DaVinci Resolve 21.0.0.48 Free",
            "transport": "embedded_lua_http_poll",
            "artifact": "/tmp/cutagent_fairlight_display_control_cm_20260619/13_direct_runtime_read_probe_after_allowlist.json",
            "candidate_methods_not_available": [
                "Timeline.GetTrackVisible('audio', index)",
                "Timeline.GetTrackVisibility('audio', index)",
                "Timeline.GetTrackColor('audio', index)",
                "Timeline.GetTrackHeight('audio', index)",
            ],
            "unsupported_bridge_count": 0,
            "probe_result": "track display getter candidates reached DaVinci Resolve and returned method_not_available",
        },
    },
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probe",
        "sampled_project_db_count": 1,
        "read_scope": "track_display_visibility_schema_probe",
        "tables": ["Sm2TiTrack"],
        "checked_columns": ["Flags", "AudioMixerBA", "FieldsBlob"],
        "checked_non_visibility_state": [
            "Sm2TiTrack.Flags",
            "Sm2TiTrack.AudioMixerBA",
            "Sm2TiTrack.FieldsBlob",
        ],
        "visibility_column_found": False,
        "fields_blob_known_payloads": ["NumLayers", "ExcludeTrackFromSequenceCaching"],
        "visibility_payload_found": False,
        "audio_enable_mute_state_is_visibility_state": False,
        "visibility_write_readback_route_found": False,
    },
    "blocker_note": (
        "Fairlight track visibility is not treated as audio enable/mute state, and no native or DB visibility "
        "read/write route is verified."
    ),
}


_FAIRLIGHT_TRACK_HEIGHT_WRITE_BLOCKER_EVIDENCE = {
    "available_db_route": "cutagent fairlight track height INDEX --json",
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db UIElementsState probe",
        "sampled_project_db_count": 1,
        "read_scope": "stored_fairlight_audio_track_display_height",
        "db_blob": "Sm2Sequence.UIElementsState",
        "blob_format_evidence": {
            "version": 9,
            "entry_count": 22,
            "key_encoding": "UTF-16BE",
            "value_encoding": "typed UI state values",
        },
        "read_keys_found": [
            "UI_SEQUENCE_AUDIO_CLIP_HEIGHT",
            "UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS",
        ],
        "db_write_probe": {
            "adjusted_track_heights_before": [0],
            "adjusted_track_heights_after": [220],
            "audio_clip_height_before": 70,
            "audio_clip_height_after": 160,
            "db_values_persisted_after_project_reload": True,
            "gui_resize_verified_after_reload": False,
        },
        "height_readback_route_found": True,
        "height_write_readback_route_found": False,
        "resolve_21_gui_resize_recheck_2026_06_20": {
            "artifact_dir": "/tmp/cutagent_track_height_gui_research_20260620",
            "timeline": "CUTAGENT_CLIP_EDIT_RENDER_PROOF_052848",
            "gui_resize_visible": True,
            "public_height_readback_after_gui_resize": {
                "audio_clip_height": 70,
                "track_adjusted_height": 0,
                "all_track_adjusted_heights": [0],
            },
            "changed_db_tables_after_gui_resize": ["SM_Config", "SM_Project", "Sm2Sequence"],
            "changed_payload": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            "ui_elements_state_height_keys_changed": False,
            "safe_fieldsblob_resize_model_found": False,
        },
        "resolve_21_reverse_db_write_probe_2026_06_20": {
            "artifact_dir": "/tmp/cutagent_track_height_gui_research_20260620",
            "writer_artifact": "12_db_write_offset_210753_to_0x66.json",
            "restore_artifact": "16_restore_offset_210753_to_0x00.json",
            "timeline": "CUTAGENT_CLIP_EDIT_RENDER_PROOF_052848",
            "candidate_decompressed_offset": 210753,
            "candidate_byte_before": 0,
            "candidate_byte_after": 102,
            "db_session_steps": [
                "save_project",
                "backup_project_db",
                "close_project",
                "sqlite_commit",
                "reopen_project",
                "restore_timeline",
                "verify",
            ],
            "db_readback_verified": True,
            "gui_resize_verified_after_reopen": False,
            "restored_candidate_byte_after_probe": True,
        },
    },
    "height_model_evidence": {
        "db_blob": "Sm2Sequence.UIElementsState",
        "read_keys": [
            "UI_SEQUENCE_AUDIO_CLIP_HEIGHT",
            "UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS",
        ],
        "height_read_supported": True,
        "db_write_probe_persisted": True,
        "gui_resize_verified": False,
        "resolve_21_gui_resize_payload": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "resolve_21_gui_resize_readback_mapped": False,
        "reverse_fieldsblob_write_verified_db_but_not_gui": True,
        "set_supported": False,
        "probe_result": (
            "DB writes to UIElementsState persisted but did not resize the Fairlight GUI after project reload; "
            "a DaVinci Resolve 21 GUI resize changed opaque Sm2Sequence.FieldsBlob.FLStudioModelBA bytes instead. "
            "A reverse write of the only changed decompressed byte verified in Project.db after reopen, but did not "
            "recreate the visible GUI resize."
        ),
    },
    "native_probe_evidence": {
        "runtime": "DaVinci Resolve 20 Free",
        "candidate_methods": ["Timeline.GetTrackHeight('audio', index)"],
        "probe_result": "method not available",
        "height_native_read_supported": False,
        "height_native_write_supported": False,
        "resolve_21_embedded_recheck": {
            "runtime": "DaVinci Resolve 21.0.0.48 Free",
            "transport": "embedded_lua_http_poll",
            "artifact": "/tmp/cutagent_fairlight_display_control_cm_20260619/13_direct_runtime_read_probe_after_allowlist.json",
            "candidate_methods_not_available": [
                "Timeline.GetTrackHeight('audio', index)",
            ],
            "unsupported_bridge_count": 0,
            "probe_result": "track-height getter candidate reached DaVinci Resolve and returned method_not_available",
        },
    },
    "blocker_note": (
        "Stored UIElementsState height readback is supported, but resize writes are not claimed. Persisted "
        "UIElementsState writes did not change the visible Fairlight GUI, and current DaVinci Resolve 21 GUI resize "
        "writes an opaque FLStudioModelBA payload that is not safely mapped. A reverse DB-session write of the "
        "candidate GUI-diff byte verified at rest but did not change the reopened Fairlight GUI height."
    ),
}


_FAIRLIGHT_TRACK_FOLDER_BLOCKER_EVIDENCE = {
    "official_resolve_21_evidence": {
        "source": "Blackmagic Design support downloads API and DaVinci Resolve 21 public feature pages",
        "support_api_checked_at": "2026-06-12",
        "public_sources": [
            "https://www.blackmagicdesign.com/products/davinciresolve/whatsnew",
            "https://www.blackmagicdesign.com/products/davinciresolve/fairlight",
        ],
        "latest_free_release": {
            "name": "DaVinci Resolve 21.0",
            "release_id": "6aefbffe870f4ba686e61ecb83b19ec0",
            "download_id": "5d486a63b17f4cbabd07b6d6d364e27c",
            "mac_build": 48,
        },
        "feature_scope": "Fairlight Folder Tracks",
        "documented_user_workflow": [
            "select two or more tracks on the Fairlight page",
            "right-click one selected track",
            "choose Add Tracks to New Folder",
            "delete the folder track to restore original track positions",
        ],
        "documented_semantics": [
            "group tracks into a composite Fairlight timeline view",
            "collapse and reopen the folder track",
            "rename folder track",
            "folder-level solo and mute",
            "up to three folder nesting levels",
        ],
    },
    "local_runtime_evidence": {
        "installed_app_checked_at": "2026-06-12",
        "installed_version": "21.0.0",
        "installed_build": "21.0.00048",
        "resolve_21_folder_track_live_probe_available": True,
        "live_probe_project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
        "live_probe_timeline": "FL_PARITY_24FPS",
        "gui_fixture_project": "CUTAGENT_RESOLVE21_FOLDER_PROBE_20260612_173908",
        "gui_fixture_timeline": "FOLDER_PROBE_24FPS",
    },
    "native_probe_evidence": {
        **_FAIRLIGHT_RESOLVE21_NATIVE_PROBE_CONTEXT,
        "candidate_methods_not_available": [
            "Timeline.GetTrackFolderList('audio')",
            "Timeline.GetTrackFolders('audio')",
            "Timeline.GetTrackFolderInfo('audio', 1)",
            "Timeline.GetTrackFolderMembership('audio', 1)",
            "Timeline.GetTrackFolderCollapsed('audio', 1)",
        ],
        "mutating_candidates_not_called": [
            "Timeline.CreateTrackFolder('audio', track_indices, name)",
            "Timeline.AddTracksToFolder('audio', track_indices, folder_index)",
            "Timeline.SetTrackFolderCollapsed('audio', folder_index, collapsed)",
            "Timeline.RemoveTrackFolder('audio', folder_index)",
        ],
        "probe_result": "DaVinci Resolve 21 embedded Lua bridge returned method_not_available for folder-track getters",
        "mutating_candidates_called": False,
        "reason": "folder-track mutation candidates were not called because no native readback route is exposed",
        "folder_track_native_read_supported": False,
        "folder_track_native_write_supported": False,
    },
    "resolve_21_gui_db_diff_evidence": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "project": "CUTAGENT_RESOLVE21_FOLDER_PROBE_20260612_173908",
        "timeline": "FOLDER_PROBE_24FPS",
        "fixture_action": "selected A1 and A2 on the Fairlight page and used Add Tracks to New Folder",
        "visual_readback": "Fairlight GUI showed Folder 1 containing A1/A2 plus mixer strip F1",
        "before_db_snapshot": "/tmp/CUTAGENT_RESOLVE21_FOLDER_PROBE_20260612_173908_before_folder.Project.db",
        "after_db_snapshot": (
            "~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Resolve Project Library/"
            "Resolve Projects/Users/guest/Projects/CUTAGENT_RESOLVE21_FOLDER_PROBE_20260612_173908/Project.db"
        ),
        "tables_added": [],
        "tables_removed": [],
        "table_counts_unchanged": {
            "Sm2TiTrack": 4,
            "Sm2Sequence": 1,
            "Sm2SequenceContainer": 1,
            "Sm2Timeline": 1,
            "SM_Group": 0,
            "SM_GroupList": 0,
        },
        "sm2_titrack_rows_changed": False,
        "ui_elements_state_changed": False,
        "changed_payload": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "fields_blob_len_before": 11490,
        "fields_blob_len_after": 11516,
        "compressed_fairlight_model_size_before": 8649,
        "compressed_fairlight_model_size_after": 8675,
        "decompressed_fairlight_model_len_before": 365728,
        "decompressed_fairlight_model_len_after": 365728,
        "decompressed_diff_byte_count": 26,
        "decompressed_diff_run_count": 20,
        "changed_offsets_observed": [
            207065,
            207069,
            207073,
            215053,
            215061,
            215065,
            216873,
            216881,
            309645,
            311673,
            311961,
            311993,
            312585,
            352744,
            362428,
            362840,
            363252,
            364496,
            364908,
            365320,
        ],
        "label_pool_note": (
            "ASCII label-pool strings such as Folder 1 through Folder 100 were already present before the GUI "
            "folder was created, so those tokens are not treated as active folder membership readback."
        ),
        "db_read_supported": False,
        "db_write_supported": False,
        "probe_result": (
            "The GUI-created folder track persisted only as small internal FLStudioModelBA offset changes; no "
            "named table, track row, membership join, collapse-state column, or stable readback schema was found."
        ),
    },
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db samples plus DaVinci Resolve 21-opened local Project.db samples",
        "sampled_project_db_count": 5,
        "resolve_21_opened_project_db_count": 2,
        "read_scope": "resolve_20_and_resolve_21_negative_track_folder_schema_probe",
        "candidate_tables_checked": [
            "Sm2TiTrack",
            "Sm2Sequence_Sm2TiTrack",
            "Sm2TiTrackGroup",
            "Sm2TiTrackFolder",
            "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        ],
        "folder_track_table_found_in_samples": False,
        "folder_label_pool_seen": True,
        "folder_label_pool_is_membership_readback": False,
        "gui_created_folder_changed_named_table": False,
        "gui_created_folder_changed_sm2_titrack_rows": False,
        "gui_created_folder_changed_ui_elements_state": False,
        "gui_created_folder_changed_fairlight_model_blob": True,
        "track_folder_membership_schema_found_in_samples": False,
        "collapse_state_schema_found_in_samples": False,
        "folder_level_solo_mute_schema_found_in_samples": False,
        "write_readback_route_found": False,
    },
    "db_blocker_note": (
        "DaVinci Resolve 21 introduces Fairlight folder tracks, but the DaVinci Resolve 21 embedded Lua bridge did not "
        "expose folder-track getter methods and local DaVinci Resolve 20/21 Project.db samples do not contain a verified "
        "folder-track membership/collapse/write schema. A GUI-created DaVinci Resolve 21 folder track changed only small "
        "internal offsets inside Sm2Sequence.FieldsBlob.FLStudioModelBA; preexisting Folder label-pool strings were "
        "not active membership readback. CutAgent CLI therefore keeps this as an explicit unsupported "
        "residual until a native API or DB-backed route can be live-verified."
    ),
}


@track_app.command("folder")
@handle_errors
def track_folder(
    tracks: list[int] = typer.Argument(..., min=1, help="Audio track indices to place in a Fairlight folder"),
    name: str | None = typer.Option(None, "--name", help="Requested Fairlight folder track name"),
    collapse: bool = typer.Option(False, "--collapse/--open", help="Requested initial folder collapsed state"),
):
    """Report DaVinci Resolve 21 Fairlight folder-track API availability."""
    enforce_mutation_policy("fairlight.track_folder", intended_engine="not_available", mutating=False)
    normalized_tracks = [int(track) for track in tracks]
    if len(normalized_tracks) < 2:
        raise ValidationError(
            "Fairlight folder tracks require at least two audio tracks.",
            details={"tracks": normalized_tracks, "min_tracks": 2},
            recoverability="not_applicable",
        )
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.track_folder",
        workflow="DaVinci Resolve 21 Fairlight folder tracks",
        requested={"tracks": normalized_tracks, "name": name, "collapse": bool(collapse)},
        required_native_api=[
            "create a Fairlight folder track from selected audio tracks",
            "read Fairlight folder track membership",
            "set Fairlight folder collapse/open state",
            "delete a folder track while restoring member track positions",
        ],
        api_note=(
            "Fairlight folder tracks are a DaVinci Resolve 21 feature. The local verified runtime is "
            "DaVinci Resolve 21.0.0.48 Free, and no native API or stable DB-backed route has been live-verified "
            "for folder-track creation, membership, collapse state, or deletion."
        ),
        workaround="Create and manage Fairlight folder tracks manually in DaVinci Resolve 21 until a verified native or DB route exists.",
        extra_details=_FAIRLIGHT_TRACK_FOLDER_BLOCKER_EVIDENCE,
    )


@track_app.command("show")
@handle_errors
def track_show(index: int = typer.Argument(..., min=1, help="Audio track index to show")):
    """Report Fairlight track visibility API availability."""
    enforce_mutation_policy("fairlight.track_visibility", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.track_visibility",
        workflow="Fairlight track show",
        requested={"index": int(index), "visible": True},
        required_native_api=[
            "show/hide an audio track in the Fairlight timeline",
            "read Fairlight track visibility",
            "persist track display visibility without mutating audio enable state",
        ],
        api_note="Fairlight track visibility is a UI timeline layout state and is not exposed by the DaVinci Resolve scripting API.",
        workaround="Use `fairlight mute/unmute` for audible state through the API, or show/hide the track in DaVinci Resolve manually.",
        extra_details=_FAIRLIGHT_TRACK_VISIBILITY_BLOCKER_EVIDENCE,
    )


@track_app.command("hide")
@handle_errors
def track_hide(index: int = typer.Argument(..., min=1, help="Audio track index to hide")):
    """Report Fairlight track visibility API availability."""
    enforce_mutation_policy("fairlight.track_visibility", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.track_visibility",
        workflow="Fairlight track hide",
        requested={"index": int(index), "visible": False},
        required_native_api=[
            "show/hide an audio track in the Fairlight timeline",
            "read Fairlight track visibility",
            "persist track display visibility without mutating audio enable state",
        ],
        api_note="Fairlight track visibility is a UI timeline layout state and is not exposed by the DaVinci Resolve scripting API.",
        workaround="Use `fairlight mute/unmute` for audible state through the API, or show/hide the track in DaVinci Resolve manually.",
        extra_details=_FAIRLIGHT_TRACK_VISIBILITY_BLOCKER_EVIDENCE,
    )


@track_app.command("height")
@handle_errors
def track_height(
    index: int = typer.Argument(..., min=1, help="Audio track index"),
    size: str | None = typer.Option(None, "--size", help="Requested track height preset or pixel value"),
):
    """Read Fairlight track height state, or report resize API availability."""
    if size is None:
        enforce_mutation_policy("fairlight.track_height", intended_engine="db_workaround", mutating=False)
        if is_dry_run():
            set_execution_engine("db_workaround")
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                {
                    "action": "fairlight.track.height.read",
                    "dry_run": True,
                    "runtime_read_called": False,
                    "route": "db_workaround",
                    "target": {"kind": "audio_track", "index": int(index)},
                    "db_blob": "Sm2Sequence.UIElementsState",
                    "read_keys": [
                        "UI_SEQUENCE_AUDIO_CLIP_HEIGHT",
                        "UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS",
                    ],
                    "read_scope": "stored_fairlight_audio_track_display_height",
                    "set_supported": False,
                    "preflight_command": f"cutagent fairlight track height {int(index)} --json",
                },
                title="Fairlight Track Height Plan",
            )
            return
        conn = get_connection(require_timeline=True)
        _validate_audio_track_index(conn, index)
        data = fairlight_ops.read_audio_track_height_state(conn, int(index))
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(data, title="Fairlight Track Height")
        return

    _raise_fairlight_native_unavailable(
        capability_id="fairlight.track_height",
        workflow="Fairlight track height/display size",
        requested={"index": int(index), "size": size},
        required_native_api=[
            "set Fairlight audio track height",
            "read live Fairlight GUI track height after resize",
            "persist per-track display size",
        ],
        api_note=(
            "DaVinci Resolve 20 Free does not expose a Fairlight track-height scripting method. "
            "Sm2Sequence.UIElementsState exposes read-only audio height keys, but local DB writes "
            "to UI_SEQUENCE_AUDIO_CLIP_HEIGHT and UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS "
            "persisted without changing the Fairlight GUI after project reload. A current DaVinci Resolve 21 GUI resize "
            "changed Sm2Sequence.FieldsBlob.FLStudioModelBA instead, but no safe write/readback model is mapped."
        ),
        workaround=(
            "Run `fairlight track height INDEX --json` to read stored UIElementsState height values, "
            "or adjust Fairlight track height in DaVinci Resolve until a verified native/DB resize route exists."
        ),
        extra_details=_FAIRLIGHT_TRACK_HEIGHT_WRITE_BLOCKER_EVIDENCE,
    )


@track_app.command("input-monitor")
@handle_errors
def track_input_monitor(
    index: int = typer.Argument(..., min=1, help="Audio track index"),
    enable: bool = typer.Option(True, "--enable/--disable", help="Requested input monitoring state"),
):
    """Report Fairlight input monitoring API availability."""
    enforce_mutation_policy("fairlight.input_monitoring", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.input_monitoring",
        workflow="Fairlight track input monitoring",
        requested={"index": int(index), "enable": bool(enable)},
        required_native_api=[
            "enable/disable input monitoring on an audio track",
            "read input monitoring state",
            "route hardware input monitoring through Fairlight patch I/O",
        ],
        api_note=(
            "Fairlight input monitoring is not exposed by the DaVinci Resolve scripting API. "
            "Sampled Sm2TiTrack schemas expose track metadata and mixer blobs, but no verified per-track "
            "input-monitor, record-arm, or input-patch field."
        ),
        workaround=(
            "Patch inputs and enable monitoring in DaVinci Resolve. CutAgent CLI exposes record/input monitor "
            "blockers explicitly so agents do not attempt GUI automation."
        ),
        extra_details=_FAIRLIGHT_RECORD_INPUT_DB_BLOCKER_EVIDENCE,
    )


track_format_app = typer.Typer(help="Fairlight existing-track format operations.")
app.add_typer(track_format_app, name="track-format")


@track_format_app.command("set")
@handle_errors
def track_format_set(
    index: int = typer.Argument(..., min=1, help="Audio track index"),
    track_type: str = typer.Option("stereo", "--track-type", help="Requested audio format"),
):
    """Set an existing Fairlight audio track format in DaVinci Resolve."""
    normalized_type = _validate_audio_track_type(track_type)
    subtype = fairlight_ops.FAIRLIGHT_AUDIO_SUBTYPE_BY_TRACK_TYPE[normalized_type]
    enforce_mutation_policy(
        "fairlight.track_format_write",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.track_format.set",
                target={"kind": "audio_track", "track_type": "audio", "index": int(index)},
                changed=False,
                dry_run=True,
                runtime_write_called=False,
                requested_track_type=normalized_type,
                requested_subtype=subtype,
                route="db_native",
                db_table="Sm2TiTrack",
                db_column="SubType",
                verification_status="not_requested",
                preflight_command="cutagent fairlight tracks --json",
            ),
            title="Fairlight Track Format Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.set_audio_track_format_db(
        conn,
        index=index,
        track_type=normalized_type,
    )
    output(data, title="Fairlight Track Format")


track_order_app = typer.Typer(help="Fairlight track ordering operations.")
app.add_typer(track_order_app, name="track-order")


@track_order_app.command("move")
@handle_errors
def track_order_move(
    index: int = typer.Argument(..., min=1, help="Audio track index to move"),
    to_index: int = typer.Option(..., "--to", min=1, help="Destination audio track index"),
):
    """Move an existing Fairlight audio track in DaVinci Resolve."""
    enforce_mutation_policy(
        "fairlight.track_reorder",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.track_order.move",
                target={"kind": "audio_track", "track_type": "audio", "index": int(index)},
                changed=False,
                dry_run=True,
                runtime_write_called=False,
                index=int(index),
                to=int(to_index),
                route="db_native",
                db_relation="Sm2SequenceContainer_Sm2TiTrack.AudioTrackVec",
                verification_status="not_requested",
                preflight_command="cutagent fairlight tracks --json",
            ),
            title="Fairlight Track Order Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.move_audio_track_order_db(
        conn,
        index=index,
        to_index=to_index,
    )
    output(data, title="Fairlight Track Order")


# Note about API limitations
@app.command("note", hidden=True)
@app.command("api-notes")
@handle_errors
def api_notes():
    """Show what Fairlight features are/aren't available via the API."""
    data = fairlight_ops.get_fairlight_limitations()
    output(data, title="Fairlight API Limitations")


# ---------------------------------------------------------------------------
# Audio AI features (DB-backed, clip-level)
# ---------------------------------------------------------------------------

ai_app = typer.Typer(help="AI audio features (Voice Isolation, Dialogue Leveler, Music Remixer).")
app.add_typer(ai_app, name="ai")
