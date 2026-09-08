"""Fairlight sends, IO, groups, VCA, external process, and waveform commands."""

from __future__ import annotations

@send_app.command("list")
@handle_errors
def send_list(
    limit: int = typer.Option(50, "--limit", min=1, help="Maximum send-related token candidates to return"),
    include_context: bool = typer.Option(False, "--include-context", help="Include bounded hex/ASCII DB context around send and bus label tokens"),
    context_bytes: int = typer.Option(32, "--context-bytes", min=0, max=256, help="Bytes before/after each token when --include-context is set"),
):
    """List stored Fairlight send/aux token candidates and candidate bus destinations from the mixer model."""
    enforce_mutation_policy("fairlight.sends_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.send.list",
                "dry_run": True,
                "would_read": True,
                "route": "db_workaround",
                "target": "current_timeline_fairlight_send_tokens",
                "limit": int(limit),
                "include_context": bool(include_context),
                "context_bytes": int(context_bytes) if include_context else 0,
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "read_scope": "send_token_probe_and_bus_destinations",
                "token_probe_supported": True,
                "context_supported": True,
                "slot_state_read_supported": False,
                "assignment_supported": False,
                "set_supported": False,
            },
            title="Fairlight Sends Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.read_fairlight_send_list_db(
        conn,
        limit=limit,
        include_context=include_context,
        context_bytes=context_bytes,
    )
    output(data, title="Fairlight Sends")


@send_app.command("set")
@handle_errors
def send_set(
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Audio track index"),
    send: str | None = typer.Option(None, "--send", help="Send/bus name or slot"),
    level_db: float | None = typer.Option(None, "--level", "--level-db", help="Send level in dB"),
    pre_fader: bool | None = typer.Option(None, "--pre-fader/--post-fader", help="Requested send tap point"),
):
    """Report Fairlight send API availability."""
    enforce_mutation_policy("fairlight.sends", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.sends",
        workflow="Fairlight sends",
        requested={"track": track, "send": send, "level_db": level_db, "pre_fader": pre_fader},
        required_native_api=[
            "list Fairlight sends on a track/bus",
            "add/remove Fairlight sends",
            "set send level/pan/pre-post/mute state",
        ],
        api_note="Fairlight send slots and send parameters are not exposed by the DaVinci Resolve scripting API.",
        workaround="Configure sends in DaVinci Resolve or apply a prepared Fairlight preset until a native API or verified DB model exists.",
        extra_details=_FAIRLIGHT_SEND_SET_DB_BLOCKER_EVIDENCE,
    )


io_app = typer.Typer(help="Fairlight patch/input-output operations.")
app.add_typer(io_app, name="io")


@io_app.command("info")
@handle_errors
def io_info(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum stored patch I/O setup rows per table to read"),
):
    """Read stored Fairlight patch I/O setup rows from the DaVinci Resolve project database."""
    enforce_mutation_policy("fairlight.patch_io_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    db_tables = ["SM_AudioSettings", "SM_VTRInputSettings", "SM_VTROutputSettings", "SM_VTRConfiguration"]
    if is_dry_run():
        output(
            {
                "action": "fairlight.io.info",
                "dry_run": True,
                "limit": int(limit),
                "runtime_read_called": False,
                "route": "db_workaround",
                "db_tables": db_tables,
                "read_scope": "stored_patch_io_setup_only",
                "patch_mutation_supported": False,
                "hardware_route_probe_supported": False,
                "input_monitor_supported": False,
                "preflight_command": "cutagent fairlight io info --json",
            },
            title="Fairlight I/O Info Plan",
        )
        return
    conn = get_connection(require_project=True, require_timeline=False)
    data = fairlight_ops.read_fairlight_io_info_db(conn, limit=limit)
    output(data, title="Fairlight I/O Info")


@io_app.command("patch")
@handle_errors
def io_patch(
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Audio track index"),
    input_name: str | None = typer.Option(None, "--input", help="Hardware/input source name"),
    output_name: str | None = typer.Option(None, "--output", help="Hardware/output destination name"),
):
    """Report Fairlight patch I/O API availability."""
    enforce_mutation_policy("fairlight.patch_io", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.patch_io",
        workflow="Fairlight patch I/O",
        requested={"track": track, "input": input_name, "output": output_name},
        required_native_api=[
            "list Fairlight hardware/software inputs and outputs",
            "patch track input/output routes",
            "read record/input-monitor patch state",
        ],
        api_note=(
            "Fairlight Patch Input/Output routing is not exposed by the DaVinci Resolve scripting API. "
            "Stored patch/VTR setup rows are readable for diagnostics only and are not a verified hardware "
            "input/output mutation route."
        ),
        workaround=(
            "Patch I/O in DaVinci Resolve. CutAgent CLI can inspect tracks after recording but cannot safely "
            "change hardware routes."
        ),
        extra_details=_FAIRLIGHT_RECORD_INPUT_DB_BLOCKER_EVIDENCE,
    )


group_app = typer.Typer(help="Fairlight group and VCA operations.")
app.add_typer(group_app, name="group")


_FAIRLIGHT_GROUP_ASSIGN_DB_BLOCKER_EVIDENCE = {
    "available_db_route": (
        "`fairlight group list` reads Fairlight group label-pool entries and stored group-table rows, but this route "
        "is read-only and does not verify group creation, membership assignment, or link-option mutation semantics."
    ),
    "db_readback_command": "cutagent fairlight group list --json",
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "group_tables_present_without_verified_membership_write_route",
        "mixer_model_blob_read_by_command": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "sampled_group_tables_present": [
            "SM_Group",
            "SM_GroupList",
            "SM_Group_SM_GroupList",
            "SM_Project_Sm2Group",
            "Sm2Group",
            "Sm2GroupList",
            "Sm2Group_Sm2GroupList",
        ],
        "sampled_group_columns_seen": [
            "SM_Group.GrpId",
            "SM_Group.GrpName",
            "SM_Group.RippleMode",
            "SM_Group.Sequence",
            "Sm2Group.Name",
            "Sm2Group.FieldsBlob",
            "Sm2GroupList.FieldsBlob",
            "SM_Project_Sm2Group.DbAssociate",
        ],
        "sampled_sm2titrack_columns": [
            "Sm2TiTrack_id",
            "DbType",
            "Type",
            "SubType",
            "Flags",
            "Sequence",
            "AudioMixerBA",
            "Sm2Sequence_id",
            "UserDefinedName",
            "FieldsBlob",
            "Sm2SequenceContainer_id",
            "BaseTrack",
            "Sm2TiTrack_Owner_id",
        ],
        "active_group_row_counts_seen": {
            "SM_Group": 0,
            "SM_Group_SM_GroupList": 0,
            "SM_Project_Sm2Group": 0,
            "Sm2Group": 0,
            "Sm2GroupList": 5,
            "Sm2Group_Sm2GroupList": 0,
        },
        "group_tables_found_in_samples": True,
        "per_track_group_column_found_in_samples": False,
        "track_membership_join_to_sm2titrack_found_in_samples": False,
        "link_option_columns_found_in_samples": False,
        "group_membership_write_readback_route_found_in_samples": False,
        "candidate_tables_are_not_verified_assignment_route": True,
    },
    "group_model_evidence": {
        "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "db_tables": [
            "SM_GroupList",
            "SM_Group",
            "SM_Group_SM_GroupList",
            "Sm2GroupList",
            "Sm2Group",
            "Sm2Group_Sm2GroupList",
            "SM_Project_Sm2Group",
        ],
        "read_scope": "label_pool_and_stored_state",
        "label_pool_supported": True,
        "stored_group_state_supported": True,
        "assignment_state_in_labels": False,
        "group_create_supported": False,
        "membership_mutation_supported": False,
        "link_options_supported": False,
        "set_supported": False,
    },
    "native_probe_evidence": {
        "runtime": "DaVinci Resolve 20.3.2.9 Free",
        "transport": "embedded_lua_http_poll",
        "probe_project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
        "candidate_methods_not_available": [
            "Timeline.GetTrackGroup('audio', 1)",
        ],
        "mutating_candidates_not_called": [
            "Timeline.SetTrackGroup('audio', 1, ...)",
        ],
        "resolve_21_embedded_recheck": {
            "runtime": "DaVinci Resolve 21.0.0.48 Free",
            "transport": "embedded_lua_http_poll",
            "artifact": "/tmp/cutagent_send_group_vca_co_20260619/08_direct_send_group_vca_probe_after_allowlist.json",
            "candidate_methods_not_available": [
                "Timeline.GetTrackGroup('audio', 1)",
                "Timeline.GetFairlightGroups()",
                "Timeline.GetGroupList()",
            ],
            "unsupported_bridge_count": 0,
            "probe_result": "group getter candidates reached DaVinci Resolve and returned method_not_available",
        },
        "probe_result": "group getter returned method_not_available; mutating group candidate was not called",
        "membership_native_read_supported": False,
        "membership_native_write_supported": False,
    },
    "db_blocker_note": (
        "Readable label pools and stored group-table rows are not treated as a safe group assignment route until "
        "active membership semantics and write/readback verification are proven."
    ),
}


@group_app.command("list")
@handle_errors
def group_list(
    limit: int = typer.Option(50, "--limit", min=1, help="Maximum stored group-table rows per table to read"),
):
    """List Fairlight group labels from the Disk DB mixer model."""
    enforce_mutation_policy("fairlight.group_read", intended_engine="db_workaround", mutating=False)
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.group.list",
                "dry_run": True,
                "would_read": True,
                "route": "db_workaround",
                "target": "current_timeline_fairlight_group_state",
                "limit": int(limit),
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "db_tables": [
                    "SM_GroupList",
                    "SM_Group",
                    "SM_Group_SM_GroupList",
                    "Sm2GroupList",
                    "Sm2Group",
                    "Sm2Group_Sm2GroupList",
                    "SM_Project_Sm2Group",
                ],
                "read_scope": "label_pool_and_stored_state",
                "assignment_supported": False,
                "set_supported": False,
            },
            title="Fairlight Groups Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.read_fairlight_group_list_db(conn, limit=limit)
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    output(data, title="Fairlight Groups")


@group_app.command("assign")
@handle_errors
def group_assign(
    group: str | None = typer.Argument(None, help="Track group name"),
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Audio track index"),
):
    """Report Fairlight track group API availability."""
    enforce_mutation_policy("fairlight.groups", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.groups",
        workflow="Fairlight track groups",
        requested={"group": group, "track": track},
        required_native_api=[
            "create/delete Fairlight track groups",
            "assign/unassign tracks to groups",
            "read group membership and link options",
        ],
        api_note="Fairlight track group membership is not exposed by the DaVinci Resolve scripting API.",
        workaround="Manage Fairlight groups in DaVinci Resolve; use cutagent for supported per-track state changes.",
        extra_details=_FAIRLIGHT_GROUP_ASSIGN_DB_BLOCKER_EVIDENCE,
    )


vca_app = typer.Typer(help="Fairlight VCA operations.")
app.add_typer(vca_app, name="vca")


_FAIRLIGHT_VCA_ASSIGN_DB_BLOCKER_EVIDENCE = {
    "available_db_route": (
        "`fairlight vca list` reads Fairlight VCA label-pool entries from the timeline mixer model, but this route "
        "is read-only and does not verify VCA assignment or fader/mute/solo mutation semantics."
    ),
    "db_readback_command": "cutagent fairlight vca list --json",
    "db_schema_evidence": {
        "source": "local Project.db schema probe",
        "sampled_project_db_count": 1,
        "read_scope": "negative_vca_schema_probe",
        "sampled_tables_matching_vca": [],
        "sampled_group_tables_present": [
            "SM_Group",
            "SM_GroupList",
            "SM_Group_SM_GroupList",
            "SM_Project_Sm2Group",
            "Sm2Group",
            "Sm2GroupList",
            "Sm2Group_Sm2GroupList",
        ],
        "sampled_sm2titrack_columns": [
            "Sm2TiTrack_id",
            "DbType",
            "Type",
            "SubType",
            "Flags",
            "Sequence",
            "AudioMixerBA",
            "Sm2Sequence_id",
            "UserDefinedName",
            "FieldsBlob",
            "Sm2SequenceContainer_id",
            "BaseTrack",
            "Sm2TiTrack_Owner_id",
        ],
        "vca_assignment_table_found": False,
        "vca_control_table_found": False,
        "per_track_vca_column_found": False,
    },
    "vca_model_evidence": {
        "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "read_scope": "labels_only",
        "label_pool_supported": True,
        "assignment_state_in_labels": False,
        "vca_create_supported": False,
        "assignment_mutation_supported": False,
        "fader_state_supported": False,
        "mute_solo_state_supported": False,
        "set_supported": False,
    },
    "native_probe_evidence": {
        "runtime": "DaVinci Resolve 20.3.2.9 Free",
        "transport": "embedded_lua_http_poll",
        "probe_project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
        "candidate_methods_not_available": [
            "Timeline.GetTrackVCA('audio', 1)",
        ],
        "mutating_candidates_not_called": [
            "Timeline.SetTrackVCA('audio', 1, ...)",
        ],
        "resolve_21_embedded_recheck": {
            "runtime": "DaVinci Resolve 21.0.0.48 Free",
            "transport": "embedded_lua_http_poll",
            "artifact": "/tmp/cutagent_send_group_vca_co_20260619/08_direct_send_group_vca_probe_after_allowlist.json",
            "candidate_methods_not_available": [
                "Timeline.GetTrackVCA('audio', 1)",
                "Timeline.GetFairlightVCAs()",
                "Timeline.GetVCAList()",
            ],
            "unsupported_bridge_count": 0,
            "probe_result": "VCA getter candidates reached DaVinci Resolve and returned method_not_available",
        },
        "probe_result": "VCA getter returned method_not_available; mutating VCA candidate was not called",
        "assignment_native_read_supported": False,
        "assignment_native_write_supported": False,
    },
    "db_blocker_note": (
        "Readable VCA label-pool entries are not treated as active VCA assignment or control state until "
        "membership/control semantics and write/readback verification are proven."
    ),
}


@vca_app.command("list")
@handle_errors
def vca_list():
    """List Fairlight VCA labels from the Disk DB mixer model."""
    enforce_mutation_policy("fairlight.vca_read", intended_engine="db_workaround", mutating=False)
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.vca.list",
                "dry_run": True,
                "would_read": True,
                "route": "db_workaround",
                "target": "current_timeline_fairlight_vca_labels",
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "read_scope": "labels_only",
                "label_pool_supported": True,
                "assignment_supported": False,
                "fader_state_supported": False,
                "mute_solo_state_supported": False,
                "set_supported": False,
            },
            title="Fairlight VCAs Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.read_fairlight_vca_list_db(conn)
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    output(data, title="Fairlight VCAs")


@vca_app.command("assign")
@handle_errors
def vca_assign(
    vca: str | None = typer.Argument(None, help="VCA name"),
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Audio track index"),
):
    """Report Fairlight VCA API availability."""
    enforce_mutation_policy("fairlight.vca", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.vca",
        workflow="Fairlight VCA assignment",
        requested={"vca": vca, "track": track},
        required_native_api=[
            "create/delete Fairlight VCAs",
            "assign/unassign tracks to VCAs",
            "read/write VCA level/mute/solo state",
        ],
        api_note="Fairlight VCA creation, assignment, and level control are not exposed by the DaVinci Resolve scripting API.",
        workaround="Manage VCAs in DaVinci Resolve until a native API or verified DB model exists.",
        extra_details=_FAIRLIGHT_VCA_ASSIGN_DB_BLOCKER_EVIDENCE,
    )


external_process_app = typer.Typer(help="Fairlight external audio process operations.")
app.add_typer(external_process_app, name="external-process")


_FAIRLIGHT_EXTERNAL_PROCESS_RUN_BLOCKER_EVIDENCE = {
    "available_config_route": (
        "`fairlight external-process list` reads configured external-process entries from DaVinci Resolve's "
        "Fairlight XML configuration, but this route is read-only and does not verify launch or round-trip semantics."
    ),
    "config_readback_command": "cutagent fairlight external-process list --json",
    "available_read_routes": [
        {
            "command": "cutagent fairlight external-process list --json",
            "route": "workaround_setting",
            "scope": "read configured Fairlight external-process XML entries",
            "config_path_hint": "Fairlight/Effects/ExternalFXConfiguration.xml",
        }
    ],
    "external_process_model_evidence": {
        "config_path_hint": "Fairlight/Effects/ExternalFXConfiguration.xml",
        "read_scope": "external_process_configuration_xml",
        "list_supported": True,
        "run_supported": False,
        "roundtrip_supported": False,
        "set_supported": False,
        "unverified_execution_scope": [
            "clip/range handoff to configured external process",
            "external process launch trigger",
            "processed audio round-trip import",
            "timeline replacement/readback verification",
        ],
    },
    "config_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free preferences XML probe",
        "sampled_config_file_count": 1,
        "read_scope": "external_process_configuration_xml_only",
        "config_path_hint": "Fairlight/Effects/ExternalFXConfiguration.xml",
        "root_tag": "ExternalProcesses",
        "entry_tag_candidates_supported_by_reader": [
            "ExternalProcess",
            "Process",
        ],
        "entry_fields_supported_by_reader": [
            "index",
            "tag",
            "name",
            "executable",
            "arguments",
            "attributes",
            "fields",
        ],
        "configured_entry_count_in_local_sample": 0,
        "launch_trigger_schema_found_in_sample": False,
        "timeline_handoff_schema_found_in_sample": False,
        "processed_audio_roundtrip_schema_found_in_sample": False,
        "post_process_readback_route_found_in_sample": False,
        "configured_entries_are_executable_route": False,
    },
    "config_xml_evidence": {
        "source": "local DaVinci Resolve 20 Free preferences XML probe",
        "config_path_hint": "Fairlight/Effects/ExternalFXConfiguration.xml",
        "sampled_config_file_found": True,
        "root_tag": "ExternalProcesses",
        "configured_entry_count_in_local_sample": 0,
        "read_scope": "configured external-process entries only",
        "reader_entry_fields": [
            "index",
            "tag",
            "name",
            "executable",
            "arguments",
            "attributes",
            "fields",
        ],
        "sampled_entry_tags": [],
        "timeline_handoff_schema_found_in_sample": False,
        "processed_audio_roundtrip_schema_found_in_sample": False,
        "post_process_readback_route_found_in_sample": False,
    },
    "native_probe_evidence": _FAIRLIGHT_EXTERNAL_PROCESS_NATIVE_PROBE_EVIDENCE,
    "config_blocker_note": (
        "Configured process entries are not treated as executable Fairlight external-process actions until a "
        "native launch/round-trip route and readback model are proven."
    ),
}


@external_process_app.command("list")
@handle_errors
def external_process_list(
    limit: int = typer.Option(100, "--limit", min=1, help="Maximum configured external processes to read"),
):
    """List configured Fairlight external audio processes from DaVinci Resolve's Fairlight XML config."""
    enforce_mutation_policy("fairlight.external_process_read", intended_engine="workaround_setting", mutating=False)
    set_execution_engine("workaround_setting")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.external_process.list",
                "dry_run": True,
                "limit": int(limit),
                "runtime_read_called": False,
                "config_read_called": False,
                "route": "workaround_setting",
                "read_scope": "external_process_configuration_xml",
                "run_supported": False,
                "roundtrip_supported": False,
                "set_supported": False,
                "preflight_command": "cutagent fairlight external-process list --json",
            },
            title="Fairlight External Process List Plan",
        )
        return
    data = fairlight_ops.read_fairlight_external_process_config(limit=limit)
    output(data, title="Fairlight External Process List")


@external_process_app.command("run")
@handle_errors
def external_process_run(
    tool: str | None = typer.Argument(None, help="Configured external audio process name"),
    clip: str | None = typer.Option(None, "--clip", help="Timeline clip name or item id"),
):
    """Report Fairlight external audio process API availability."""
    enforce_mutation_policy("fairlight.external_process", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.external_process",
        workflow="Fairlight external audio process",
        requested={"tool": tool, "clip": clip},
        required_native_api=[
            "list configured external audio processes",
            "send a clip/range to an external processor",
            "round-trip processed audio back into the timeline",
        ],
        api_note="Fairlight external audio process configuration and round-trip execution are not exposed by the DaVinci Resolve scripting API.",
        workaround="Run external audio processing from DaVinci Resolve, or export/render audio and process files with an external CLI workflow.",
        extra_details=_FAIRLIGHT_EXTERNAL_PROCESS_RUN_BLOCKER_EVIDENCE,
    )


waveform_app = typer.Typer(help="Fairlight waveform/sample editing operations.")
app.add_typer(waveform_app, name="waveform")


_FAIRLIGHT_WAVEFORM_REPAIR_DB_BLOCKER_EVIDENCE = {
    "available_db_route": (
        "`fairlight waveform info` reads Fairlight waveform view state from `Sm2Sequence.UIElementsState`, but this "
        "route is read-only and does not verify waveform redraw, sample editing, or click/pop repair semantics."
    ),
    "db_readback_command": "cutagent fairlight waveform info --json",
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "negative_waveform_repair_schema_probe",
        "searched_table_or_column_fragments": [
            "waveform",
            "wave",
            "sample",
            "repair",
            "click",
            "pop",
            "UIElementsState",
            "audio_wf",
        ],
        "ui_state_blob_seen": "Sm2Sequence.UIElementsState",
        "ui_state_audio_keys_read_by_command": [
            "UI_SEQUENCE_AUDIO_CLIP_HEIGHT",
            "UI_SEQUENCE_USER_ADJUSTED_AUDIO_TRACK_HEIGHTS",
            "UI_SEQUENCE_AUDIO_MARK_IN",
            "UI_SEQUENCE_AUDIO_MARK_OUT",
            "UI_SEQUENCE_AUDIO_VIEW_Y_POS",
            "UI_SEQUENCE_AUDIO_WF_VIEW_OPTION",
        ],
        "audio_metadata_columns_seen": [
            "BtAudioTrackInfo.SampleRateChar",
            "Sm2MpAudioRef.SampleOffset",
            "FLAssetBaseFile.sample_rate",
            "FLAssetBaseClip.ed_wave",
            "FLAssetBaseClip.ed_wave2",
        ],
        "sampled_tables_matching_waveform_repair": [],
        "sample_editor_schema_found_in_samples": False,
        "click_pop_repair_route_found_in_samples": False,
        "waveform_redraw_route_found_in_samples": False,
        "post_repair_readback_route_found_in_samples": False,
    },
    "waveform_model_evidence": {
        "db_blob": "Sm2Sequence.UIElementsState",
        "read_scope": "audio_waveform_view_state_only",
        "waveform_view_read_supported": True,
        "waveform_redraw_supported": False,
        "sample_repair_supported": False,
        "click_repair_supported": False,
        "set_supported": False,
        "unverified_edit_scope": [
            "sample-level waveform mutation",
            "click/pop repair operation",
            "waveform edit history",
            "post-repair audio readback verification",
        ],
    },
    "native_probe_evidence": _FAIRLIGHT_WAVEFORM_NATIVE_PROBE_EVIDENCE,
    "db_blocker_note": (
        "Waveform view-state readback is not treated as a Fairlight sample editor or click/pop repair route until a "
        "native API, Lua method, or verified DB mutation/readback model is proven."
    ),
}


@waveform_app.command("info")
@handle_errors
def waveform_info():
    """Read Fairlight audio waveform view state from the timeline database."""
    enforce_mutation_policy("fairlight.waveform_view_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.waveform.info",
                "dry_run": True,
                "runtime_read_called": False,
                "route": "db_workaround",
                "db_blob": "Sm2Sequence.UIElementsState",
                "read_scope": "audio_waveform_view_state_only",
                "waveform_redraw_supported": False,
                "sample_repair_supported": False,
                "preflight_command": "cutagent fairlight waveform info --json",
            },
            title="Fairlight Waveform Info Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.read_fairlight_waveform_info_db(conn)
    output(data, title="Fairlight Waveform Info")


@waveform_app.command("repair-click")
@handle_errors
def waveform_repair_click(
    clip: str | None = typer.Option(None, "--clip", help="Timeline clip name or item id"),
    at: str | None = typer.Option(None, "--at", help="Timeline/sample position to repair"),
):
    """Report Fairlight waveform/sample repair API availability."""
    enforce_mutation_policy("fairlight.waveform_editing", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.waveform_editing",
        workflow="Fairlight waveform/sample repair",
        requested={"clip": clip, "at": at},
        required_native_api=[
            "edit audio samples/waveforms directly",
            "run click/pop repair on a sample range",
            "read sample-level waveform edit history",
        ],
        api_note="Fairlight sample editor and click/pop repair operations are not exposed by the DaVinci Resolve scripting API.",
        workaround="Repair samples in DaVinci Resolve or a round-tripped external editor. CutAgent CLI can then inspect or process resulting timeline clips.",
        extra_details=_FAIRLIGHT_WAVEFORM_REPAIR_DB_BLOCKER_EVIDENCE,
    )


track_app = typer.Typer(help="Fairlight track operations that are not covered by native add/delete/state APIs.")
app.add_typer(track_app, name="track")


_FAIRLIGHT_TRACK_DUPLICATE_PARTIAL_BLOCKER_EVIDENCE = {
    "supported_subset_routes": [
        {
            "command": "cutagent fairlight track duplicate INDEX --empty --no-processing --json",
            "route": "api_native",
            "scope": "duplicate audio track shell only",
            "native_api": [
                "Timeline.GetTrackSubType",
                "Timeline.AddTrack",
                "Timeline.SetTrackName",
                "Timeline.SetTrackEnable",
                "Timeline.SetTrackLock",
            ],
        },
        {
            "command": "cutagent fairlight track duplicate INDEX --include-clips --no-processing --json",
            "route": "api_native",
            "scope": "duplicate audio track shell plus media-pool backed timeline items",
            "native_api": [
                "Timeline.GetItemListInTrack",
                "TimelineItem.GetMediaPoolItem",
                "TimelineItem.GetLeftOffset",
                "MediaPool.AppendToTimeline",
            ],
        },
        {
            "command": "cutagent fairlight track duplicate INDEX --include-clips --no-processing --copy-volume --json",
            "route": "api_native + db_workaround",
            "scope": "duplicate audio track shell, media-pool backed timeline items, and verified common Volume/fader lanes",
            "native_api": [
                "Timeline.GetTrackSubType",
                "Timeline.AddTrack",
                "Timeline.GetItemListInTrack",
                "MediaPool.AppendToTimeline",
            ],
            "db_route": [
                "read source Sm2Sequence.FieldsBlob.FLStudioModelBA fader lanes",
                "write target Sm2Sequence.FieldsBlob.FLStudioModelBA fader lanes through verified mixer fader route",
            ],
        },
        {
            "command": "cutagent fairlight track duplicate INDEX --include-clips --no-processing --copy-pan --json",
            "route": "api_native + db_workaround",
            "scope": "duplicate audio track shell, media-pool backed timeline items, and verified mono Pan lane",
            "native_api": [
                "Timeline.GetTrackSubType",
                "Timeline.AddTrack",
                "Timeline.GetItemListInTrack",
                "MediaPool.AppendToTimeline",
            ],
            "db_route": [
                "read source Sm2Sequence.FieldsBlob.FLStudioModelBA mono pan lane",
                "write target Sm2Sequence.FieldsBlob.FLStudioModelBA mono pan lane through verified mixer pan route",
            ],
        },
        {
            "command": "cutagent fairlight track duplicate INDEX --include-clips --no-processing --copy-clip-eq --json",
            "route": "api_native + db_workaround",
            "scope": "duplicate audio track shell, media-pool backed timeline items, and verified clip-level EQ EffectFiltersBA payloads",
            "native_api": [
                "Timeline.GetTrackSubType",
                "Timeline.AddTrack",
                "Timeline.GetItemListInTrack",
                "MediaPool.AppendToTimeline",
            ],
            "db_route": [
                "read source Sm2TiItem.EffectFiltersBA clip EQ payloads",
                "write target Sm2TiItem.EffectFiltersBA clip EQ payloads",
            ],
        },
        {
            "command": "cutagent fairlight track duplicate INDEX --include-clips --no-processing --copy-clip-fx --json",
            "route": "api_native + db_workaround",
            "scope": "duplicate audio track shell, media-pool backed timeline items, and verified clip-level Fairlight FX FieldsBlob payloads",
            "native_api": [
                "Timeline.GetTrackSubType",
                "Timeline.AddTrack",
                "Timeline.GetItemListInTrack",
                "MediaPool.AppendToTimeline",
            ],
            "db_route": [
                "read source Sm2TiItem.FieldsBlob FL::ClipFX payloads",
                "write target Sm2TiItem.FieldsBlob FL::ClipFX payloads",
            ],
        },
        {
            "command": "cutagent fairlight track duplicate INDEX --include-clips --no-processing --copy-color --json",
            "route": "api_native + db_workaround",
            "scope": "duplicate audio track shell, media-pool backed timeline items, and verified track color FieldsBlob payload",
            "native_api": [
                "Timeline.GetTrackSubType",
                "Timeline.AddTrack",
                "Timeline.GetItemListInTrack",
                "MediaPool.AppendToTimeline",
            ],
            "db_route": [
                "read source Sm2TiTrack.FieldsBlob.Color",
                "write target Sm2TiTrack.FieldsBlob.Color through verified track color route",
            ],
        },
    ],
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "negative_full_track_duplicate_copy_model_schema_probe",
        "supported_subset_db_fields": [
            "Sm2TiTrack.Type",
            "Sm2TiTrack.SubType",
            "Sm2TiTrack.Flags",
            "Sm2TiTrack.UserDefinedName",
            "Sm2TiItem.Sm2TiTrack_id",
            "Sm2TiItem_Sm2TiTrack.DbOwner",
            "Sm2TiItem_Sm2TiTrack.DbAssociate",
            "Sm2TiItem_Sm2TiTrack.DbIndex",
            "Sm2Sequence_Sm2TiTrack.DbOwner",
            "Sm2Sequence_Sm2TiTrack.DbAssociate",
            "Sm2Sequence_Sm2TiTrack.DbIndex",
        ],
        "opaque_track_blob_fields_seen": [
            "Sm2TiTrack.AudioMixerBA",
            "Sm2TiTrack.FieldsBlob",
            "Sm2TiItem.EffectFiltersBA",
            "Sm2TiItem.FieldsBlob",
            "Sm2Sequence.FieldsBlob",
        ],
        "clip_effect_tables_seen_but_not_track_processing_copy_model": [
            "SM_Effect",
            "SM_Clip_FilterEffects",
        ],
        "full_duplicate_copy_table_found_in_samples": False,
        "track_processing_copy_schema_found_in_samples": False,
        "routing_send_plugin_automation_copy_schema_found_in_samples": False,
        "full_duplicate_write_readback_route_found_in_samples": False,
        "gui_volume_attribute_copy_db_diff_verified": True,
        "audio_mixer_blob_copy_verified": False,
        "fields_blob_copy_verified": False,
        "unsupported_clip_layer_edge_case_copy_verified": False,
    },
    "gui_copy_paste_attributes_evidence": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "artifact_dir": "/tmp/cutagent_track_duplicate_attr_probe_20260620_062228",
        "timeline": "CUTAGENT_TRACK_DUP_ATTR_062228",
        "source_fixture": "real audio clip_edit_fixture.wav on A1 with fader -6.5 dB",
        "positive_slice": {
            "workflow": "Fairlight track header Copy Attributes -> Paste Attributes -> Track Attributes: Volume",
            "source_fader_db": -6.5,
            "target_fader_before_db": 0.0,
            "target_fader_after_db": -6.5,
            "readback_artifact": "/tmp/cutagent_track_duplicate_attr_probe_20260620_062228/34_tracks_after_paste_volume_only_apply.json",
            "db_diff": [
                "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "Sm2TiTrack.FieldsBlob on target track",
            ],
        },
        "non_promoted_scope": [
            "Copy Attributes exposes separate Volume, Mute, EQ, Dynamics, Pan, and Plugins toggles; only Volume has GUI Copy/Paste Attributes readback proof. Mono Pan, clip-level EQ, and clip-level FX are separate CLI DB subsets, not full GUI attribute-copy parity.",
            "GUI Duplicate Track... was documented by Blackmagic for Fairlight timeline tracks, but the local audited click did not create a new track in this fixture.",
            "No native/API/DB route is verified for cloning the full processing/routing/send/plugin/automation model as a single duplicate operation.",
        ],
        "track_eq_dynamics_recheck_2026_06_20": {
            "artifact_dir": "/tmp/cutagent_track_duplicate_eq_dyn_probe_20260620_091826",
            "timeline": "CUTAGENT_DUP_EQ_DYN_091826",
            "source_fixture": "real clip_edit_fixture.wav",
            "finding": (
                "Fresh EQ/Dynamics copy research did not produce a safe per-track copy route. "
                "The existing dynamics DB route has no track selector, and DaVinci Resolve 21 readback on this fixture "
                "returned out-of-range legacy offset values outside the explicitly written compressor fields."
            ),
            "not_promoted_reason": (
                "Track EQ/Dynamics duplicate parity needs a target-track-addressable model with valid readback; "
                "copying the whole FLStudioModelBA or reusing sequence-level dynamics offsets would risk corrupting "
                "unrelated mixer state."
            ),
        },
    },
    "duplicate_model_evidence": {
        "empty_no_processing_supported": True,
        "clip_copy_no_processing_supported": True,
        "track_name_format_state_supported": True,
        "gui_volume_attribute_copy_readback_supported": True,
        "volume_fader_copy_supported": True,
        "volume_fader_copy_scope": "common source fader level across mapped track channel lanes",
        "mono_pan_copy_supported": True,
        "mono_pan_copy_scope": "mono source track with verified present in-range pan lane",
        "clip_level_eq_copy_supported": True,
        "clip_level_eq_copy_scope": "Sm2TiItem.EffectFiltersBA payloads on duplicated media-pool backed timeline items",
        "clip_level_fx_copy_supported": True,
        "clip_level_fx_copy_scope": "Sm2TiItem.FieldsBlob FL::ClipFX payloads on duplicated media-pool backed timeline items",
        "mixer_processing_copy_supported": False,
        "stereo_multichannel_pan_copy_supported": False,
        "routing_copy_supported": False,
        "send_copy_supported": False,
        "plugin_insert_copy_supported": False,
        "automation_copy_supported": False,
        "unsupported_clip_layer_edge_cases_supported": False,
    },
    "native_probe_evidence": _FAIRLIGHT_TRACK_DUPLICATE_NATIVE_PROBE_EVIDENCE,
    "db_blocker_note": (
        "The supported native subset can create the destination audio track, copy basic track metadata, "
        "and append media-pool backed items without processing. No verified native API, Lua method, or DB "
        "copy model exists for duplicating mixer processing, routing, sends, plugin inserts, automation, "
        "or unsupported clip/layer edge cases as a single full Fairlight duplicate. A GUI-authored "
        "Copy/Paste Attributes probe verifies the Volume/fader slice only; it is not sufficient to promote "
        "the default full duplicate because track EQ, Dynamics, stereo/multichannel Pan, Plugins, routing, "
        "sends, and automation remain unmapped."
    ),
}
