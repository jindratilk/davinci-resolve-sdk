"""Fairlight loudness, bounce, monitor, and Elastic Wave commands."""

from __future__ import annotations

@loudness_app.command("info")
@handle_errors
def loudness_info(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum loudness-related schema/setup rows per candidate table to read"),
):
    """Read stored Fairlight loudness schema and meter setup signals."""
    enforce_mutation_policy("fairlight.loudness_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.loudness.info",
                "dry_run": True,
                "limit": int(limit),
                "runtime_read_called": False,
                "route": "db_workaround",
                "target": "current_project_loudness_schema_probe",
                "read_scope": "loudness_schema_probe_and_meter_setup_signals",
                "live_meter_values_supported": False,
                "offline_analysis_supported": False,
                "normalization_supported": False,
                "export_supported": False,
                "preflight_command": "cutagent fairlight loudness info --json",
            },
            title="Fairlight Loudness Info Plan",
        )
        return
    conn = get_connection(require_project=True, require_timeline=False)
    data = fairlight_ops.read_fairlight_loudness_info_db(conn, limit=limit)
    output(data, title="Fairlight Loudness Info")


@loudness_app.command("analyze")
@handle_errors
def loudness_analyze(
    standard: str | None = typer.Option(None, "--standard", help="Loudness standard, e.g. EBU R128 or ATSC A/85"),
):
    """Report Fairlight loudness analysis API availability."""
    enforce_mutation_policy("fairlight.loudness", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.loudness",
        workflow="Fairlight loudness analysis",
        requested={"standard": standard},
        required_native_api=[
            "read Fairlight loudness meter values",
            "run offline loudness analysis",
            "export loudness analysis results",
        ],
        api_note="Fairlight loudness meters and offline loudness analysis are not exposed by the DaVinci Resolve scripting API.",
        workaround="Use DaVinci Resolve Fairlight loudness analysis or render stems and analyze them with an external loudness tool.",
        extra_details=_FAIRLIGHT_LOUDNESS_DB_BLOCKER_EVIDENCE,
    )


@loudness_app.command("normalize")
@handle_errors
def loudness_normalize(
    target_lufs: float | None = typer.Option(None, "--target-lufs", help="Target integrated LUFS"),
):
    """Report Fairlight loudness normalization API availability."""
    enforce_mutation_policy("fairlight.loudness", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.loudness",
        workflow="Fairlight loudness normalization",
        requested={"target_lufs": target_lufs},
        required_native_api=[
            "run Fairlight loudness normalization",
            "write normalization gain decisions",
            "read true-peak/integrated LUFS result",
        ],
        api_note="Fairlight loudness normalization is not exposed by the DaVinci Resolve scripting API.",
        workaround="Normalize loudness in DaVinci Resolve or render audio and process it with an external loudness workflow.",
        extra_details=_FAIRLIGHT_LOUDNESS_DB_BLOCKER_EVIDENCE,
    )


bounce_app = typer.Typer(help="Fairlight bounce operations.")
app.add_typer(bounce_app, name="bounce")


@bounce_app.command("track")
@handle_errors
def bounce_track(
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Audio track index to bounce"),
    destination_track: int | None = typer.Option(None, "--destination-track", "--to-track", min=1, help="Existing audio track for the bounced render; omitted creates a new stereo audio track"),
    record_frame: str | None = typer.Option(None, "--record-frame", "--at", help="Record-domain placement frame/timecode; omitted uses the timeline start frame"),
    output_path: str | None = typer.Option(None, "--output", "--output-path", help="Rendered bounce media path; omitted uses the CutAgent exports folder"),
    format: str = typer.Option("MP4", "--format", help="Render format"),
    codec: str = typer.Option("H.264", "--codec", help="Render codec"),
    bitdepth: int = typer.Option(16, "--bitdepth", help="Audio bit depth"),
    samplerate: int = typer.Option(48000, "--samplerate", help="Audio sample rate"),
    clip_name: str | None = typer.Option(None, "--clip-name", help="Name to assign to the appended bounced timeline item when DaVinci Resolve allows it"),
):
    """Bounce one Fairlight audio track through native render, import, and audio-only timeline append."""
    enforce_mutation_policy("fairlight.bounce", intended_engine="api_native", mutating=not is_dry_run())
    if track is None:
        raise ValidationError(
            "--track is required for Fairlight track bounce.",
            details={
                "required": ["--track"],
                "example": "cutagent fairlight bounce track --track 1 --destination-track 2 --json",
            },
            recoverability="not_applicable",
        )
    requested = {
        "track": int(track),
        "destination_track": int(destination_track) if destination_track else None,
        "record_frame": record_frame,
        "output_path": output_path,
        "format": format,
        "codec": codec,
        "bitdepth": int(bitdepth),
        "samplerate": int(samplerate),
        "clip_name": clip_name,
    }
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.bounce.track",
                target={"kind": "audio_track", "track": int(track)},
                changed=False,
                dry_run=True,
                runtime_write_called=False,
                route="solo_render_audio_import_append",
                requested=requested,
                native_api=[
                    "Timeline.SetTrackEnable",
                    "Project.SetCurrentRenderFormatAndCodec",
                    "Project.SetRenderSettings",
                    "Project.AddRenderJob",
                    "Project.StartRendering",
                    "MediaPool.ImportMedia",
                    "MediaPool.AppendToTimeline",
                ],
                creates_destination_track=destination_track is None,
            ),
            title="Fairlight Track Bounce Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    data = fairlight_ops.bounce_track_to_track(
        conn,
        track=int(track),
        destination_track=destination_track,
        record_frame=record_frame,
        output_path=output_path,
        format=format,
        codec=codec,
        bitdepth=bitdepth,
        samplerate=samplerate,
        clip_name=clip_name,
    )
    output(mutation_payload(target={"kind": "audio_track", "track": int(track)}, **data), title="Fairlight Track Bounce")


@bounce_app.command("mix-to-track")
@handle_errors
def bounce_mix_to_track(
    bus: str | None = typer.Option(None, "--bus", help="Bus/main output to bounce"),
    destination_track: int | None = typer.Option(None, "--destination-track", "--to-track", min=1, help="Existing audio track for the bounced render; omitted creates a new stereo audio track"),
    record_frame: str | None = typer.Option(None, "--record-frame", "--at", help="Record-domain placement frame/timecode; omitted uses the timeline start frame"),
    output_path: str | None = typer.Option(None, "--output", "--output-path", help="Rendered bounce media path; omitted uses the CutAgent exports folder"),
    format: str = typer.Option("MP4", "--format", help="Render format"),
    codec: str = typer.Option("H.264", "--codec", help="Render codec"),
    bitdepth: int = typer.Option(16, "--bitdepth", help="Audio bit depth"),
    samplerate: int = typer.Option(48000, "--samplerate", help="Audio sample rate"),
    clip_name: str | None = typer.Option(None, "--clip-name", help="Name to assign to the appended bounced timeline item when DaVinci Resolve allows it"),
):
    """Bounce the main Fairlight mix through native render, import, and audio-only timeline append."""
    enforce_mutation_policy("fairlight.bounce", intended_engine="api_native", mutating=not is_dry_run())
    requested = {
        "bus": bus,
        "destination_track": int(destination_track) if destination_track else None,
        "record_frame": record_frame,
        "output_path": output_path,
        "format": format,
        "codec": codec,
        "bitdepth": int(bitdepth),
        "samplerate": int(samplerate),
        "clip_name": clip_name,
    }
    requested_bus_selector = " ".join(str(bus or "").strip().lower().split())
    if requested_bus_selector and requested_bus_selector not in {"main", "main 1", "main out", "main output", "timeline main"}:
        _raise_fairlight_native_unavailable(
            capability_id="fairlight.bus_routing",
            workflow="Fairlight non-main bus bounce source selection",
            requested={"bus": bus},
            required_native_api=[
                "select a Fairlight bus/FlexBus as a bounce render source",
                "read bus routing graph",
                "route a non-main bus to a bounced timeline track",
            ],
            api_note="DaVinci Resolve's scripting API does not expose Fairlight bus/FlexBus render source selection, and no verified DB route exists for non-main bus bounce selection.",
            workaround="Use `fairlight bounce mix-to-track` without --bus, or with --bus Main/Main 1, for the main timeline mix.",
            extra_details=_FAIRLIGHT_NON_MAIN_BUS_BOUNCE_DB_BLOCKER_EVIDENCE,
        )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.bounce.mix_to_track",
                target={"kind": "main_mix", "bus": bus or "Main"},
                changed=False,
                dry_run=True,
                runtime_write_called=False,
                route="render_audio_import_append",
                requested=requested,
                native_api=[
                    "Project.SetCurrentRenderFormatAndCodec",
                    "Project.SetRenderSettings",
                    "Project.AddRenderJob",
                    "Project.StartRendering",
                    "MediaPool.ImportMedia",
                    "MediaPool.AppendToTimeline",
                ],
                creates_destination_track=destination_track is None,
            ),
            title="Fairlight Mix Bounce Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    data = fairlight_ops.bounce_mix_to_track(
        conn,
        bus=bus,
        destination_track=destination_track,
        record_frame=record_frame,
        output_path=output_path,
        format=format,
        codec=codec,
        bitdepth=bitdepth,
        samplerate=samplerate,
        clip_name=clip_name,
    )
    output(mutation_payload(target={"kind": "main_mix", "bus": bus or "Main"}, **data), title="Fairlight Mix Bounce")


monitor_app = typer.Typer(help="Fairlight monitoring/control-room operations.")
app.add_typer(monitor_app, name="monitor")


_FAIRLIGHT_MONITOR_DB_BLOCKER_EVIDENCE = {
    "available_db_route": (
        "`fairlight monitor info` reads stored SM_UserSetup monitor/audio setup fields, "
        "but that route is read-only and does not verify live control-room level, mute, dim, "
        "speaker-set, or fold-down writes."
    ),
    "db_readback_command": "cutagent fairlight monitor info --json",
    "api_setting_snapshot_evidence": {
        "source": "Project.GetSetting()/Timeline.GetSetting() snapshot via embedded DaVinci Resolve 20.3.2 Free",
        "project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
        "timeline": "FL_PARITY_24FPS",
        "queryable_audio_monitor_keys": [
            "audioCaptureNumChannels",
            "audioOutputHasTimecode",
            "audioPlayoutNumChannels",
            "videoMonitorFormat",
            "videoPlayoutAudioFramesOffset",
            "videoPlayoutMode",
        ],
        "read_scope": "project/timeline playout and video monitor preferences only",
        "live_control_room_level_supported": False,
        "live_control_room_mute_supported": False,
        "control_room_dim_supported": False,
    },
    "db_schema_evidence": {
        "sampled_resolve_edition": "DaVinci Resolve 20 Free",
        "sampled_project_db_count": 3,
        "stored_monitor_setup_table": "SM_UserSetup",
        "read_scope": "stored_monitor_setup_only",
        "sampled_sm_usersetup_audio_columns": [
            "TargetMonitor",
            "EnableAudio",
            "MuteAudio",
            "MasterAudioDisable",
            "AudioMeterDBUEnable",
            "AudioMeterAlignmentLevel",
        ],
        "unverified_write_columns": [
            "MuteAudio",
            "MasterAudioDisable",
            "EnableAudio",
        ],
        "unmapped_control_room_concepts": [
            "live monitor level",
            "monitor dim",
            "speaker set",
            "fold-down",
        ],
    },
    "native_probe_evidence": _FAIRLIGHT_MONITOR_NATIVE_PROBE_EVIDENCE,
}


@monitor_app.command("info")
@handle_errors
def monitor_info(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum stored monitor setup rows to read"),
):
    """Read stored Fairlight monitor/audio setup rows from the DaVinci Resolve project database."""
    enforce_mutation_policy("fairlight.monitoring_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.monitor.info",
                "dry_run": True,
                "limit": int(limit),
                "runtime_read_called": False,
                "route": "db_workaround",
                "db_tables": ["SM_UserSetup"],
                "read_scope": "stored_monitor_setup_only",
                "live_level_supported": False,
                "live_mute_supported": False,
                "dim_supported": False,
                "speaker_set_supported": False,
                "fold_down_supported": False,
                "set_supported": False,
                "preflight_command": "cutagent fairlight monitor info --json",
            },
            title="Fairlight Monitor Info Plan",
        )
        return
    conn = get_connection(require_project=True, require_timeline=False)
    data = fairlight_ops.read_fairlight_monitor_info_db(conn, limit=limit)
    output(data, title="Fairlight Monitor Info")


@monitor_app.command("level")
@handle_errors
def monitor_level(
    level_db: float | None = typer.Option(None, "--level", "--level-db", help="Monitor/control-room level in dB"),
):
    """Report Fairlight monitor level API availability."""
    enforce_mutation_policy("fairlight.monitoring", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.monitoring",
        workflow="Fairlight monitor level control",
        requested={"level_db": level_db},
        required_native_api=[
            "read/set control-room monitor level",
            "dim/mute monitor output",
            "configure fold-down or speaker set",
        ],
        api_note=(
            "Fairlight monitoring/control-room controls are not exposed by the DaVinci Resolve scripting API. "
            "Stored SM_UserSetup audio fields are readable for setup diagnostics only and are not a verified "
            "live monitor-control mutation route."
        ),
        workaround="Control monitoring in DaVinci Resolve or external audio hardware; CutAgent CLI cannot safely infer or change hardware monitor state.",
        extra_details=_FAIRLIGHT_MONITOR_DB_BLOCKER_EVIDENCE,
    )


@monitor_app.command("mute")
@handle_errors
def monitor_mute(
    enable: bool = typer.Option(True, "--enable/--disable", help="Requested monitor mute state"),
):
    """Report Fairlight monitor mute API availability."""
    enforce_mutation_policy("fairlight.monitoring", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.monitoring",
        workflow="Fairlight monitor mute control",
        requested={"enable": bool(enable)},
        required_native_api=[
            "mute/unmute control-room monitor output",
            "read monitor mute/dim state",
        ],
        api_note=(
            "Fairlight monitoring/control-room mute state is not exposed by the DaVinci Resolve scripting API. "
            "SM_UserSetup.MuteAudio and SM_UserSetup.MasterAudioDisable are readable setup fields, but local "
            "DaVinci Resolve 20 Free evidence does not verify them as safe live control-room mute/dim write controls."
        ),
        workaround=(
            "Use DaVinci Resolve or hardware monitor controls directly; use `fairlight monitor info --json` "
            "only for stored setup readback."
        ),
        extra_details=_FAIRLIGHT_MONITOR_DB_BLOCKER_EVIDENCE,
    )


def _build_fairlight_elastic_segment_timemap(
    *,
    duration_frames: int,
    fps: float,
    points: tuple[retime_db.TimeMapPoint, ...],
) -> retime_db.SpeedRampTimeMap:
    safe_duration = int(duration_frames)
    safe_fps = float(fps or 25.0)
    if safe_duration <= 1:
        raise ValidationError(
            "Fairlight Elastic segment mapping requires an audio clip of at least 2 frames.",
            details={"duration_frames": duration_frames},
            recoverability="not_applicable",
        )
    x_max = (safe_duration - 1) / safe_fps
    point_tolerance = 1e-6
    normalized = list(points)
    if not normalized:
        raise ValidationError(
            "Fairlight Elastic segment mapping requires at least one --time-point.",
            details={"point_count": 0},
            recoverability="not_applicable",
        )
    if all(abs(point.x) > point_tolerance for point in normalized):
        normalized.append(retime_db.TimeMapPoint(0, 0.0, 0.0))
    if all(abs(point.x - x_max) > point_tolerance for point in normalized):
        normalized.append(retime_db.TimeMapPoint(len(normalized), x_max, x_max))
    normalized.sort(key=lambda point: point.x)
    normalized = [
        retime_db.TimeMapPoint(
            point.index,
            0.0 if abs(point.x) <= point_tolerance else (x_max if abs(point.x - x_max) <= point_tolerance else point.x),
            0.0 if abs(point.y) <= point_tolerance else (x_max if abs(point.y - x_max) <= point_tolerance else point.y),
            interp=point.interp,
            x_in=point.x_in,
            y_in=point.y_in,
            x_out=point.x_out,
            y_out=point.y_out,
        )
        for point in normalized
    ]
    previous_x = -math.inf
    previous_y = -math.inf
    for point in normalized:
        if point.x < -point_tolerance or point.x > x_max + point_tolerance:
            raise ValidationError(
                "Fairlight Elastic segment output time x must be inside the clip duration.",
                details={"point": point.to_dict(), "x_max_seconds": x_max},
                recoverability="not_applicable",
            )
        if point.y < -point_tolerance or point.y > x_max + point_tolerance:
            raise ValidationError(
                "Fairlight Elastic segment source time y must be inside the clip source duration.",
                details={"point": point.to_dict(), "source_max_seconds": x_max},
                recoverability="not_applicable",
            )
        if point.x <= previous_x + point_tolerance:
            raise ValidationError(
                "Fairlight Elastic segment output times must be strictly increasing.",
                details={"point": point.to_dict()},
                recoverability="not_applicable",
            )
        if point.y < previous_y - point_tolerance:
            raise ValidationError(
                "Fairlight Elastic segment source times must not move backwards.",
                details={"point": point.to_dict()},
                recoverability="not_applicable",
            )
        previous_x = point.x
        previous_y = point.y
    if abs(normalized[0].x) > point_tolerance or abs(normalized[0].y) > point_tolerance:
        raise ValidationError(
            "Fairlight Elastic segment mapping must start at x=0,y=0.",
            details={"first_point": normalized[0].to_dict()},
            recoverability="not_applicable",
        )
    if abs(normalized[-1].x - x_max) > point_tolerance or abs(normalized[-1].y - x_max) > point_tolerance:
        raise ValidationError(
            "Fairlight Elastic segment mapping must end at the clip end; use --ratio for whole-clip duration changes.",
            details={"last_point": normalized[-1].to_dict(), "clip_end_seconds": x_max},
            recoverability="not_applicable",
        )
    return retime_db.build_explicit_speed_ramp_timemap(
        safe_duration,
        safe_fps,
        points=tuple(normalized),
        direction="outgoing",
        curve="fairlight-elastic-segment",
    )


def _fairlight_decoded_timemap_points(blob: bytes) -> list[dict[str, float | int]] | None:
    decoded = retime_db.decode_timemap_blob(blob)
    try:
        keyframes_ba = decoded["decoded"]["entries"]["KeyframesBA"]["decoded"]
    except (KeyError, TypeError):
        return None
    if isinstance(keyframes_ba, dict) and keyframes_ba.get("type") == "RetimeKeyframeListProto":
        return [
            {
                "x": float(point["x"]),
                "y": float(point["y"]),
                "x_in": float(point.get("x_in", 0.0)),
                "y_in": float(point.get("y_in", 0.0)),
                "x_out": float(point.get("x_out", 0.0)),
                "y_out": float(point.get("y_out", 0.0)),
                "interp": int(point.get("interp", 0)),
            }
            for point in (keyframes_ba.get("keyframes") or [])
        ]
    if isinstance(keyframes_ba, dict) and keyframes_ba.get("type") == "Sm2TimeMapLegacyKeyframes":
        return [
            {
                "x": float(point["x"]),
                "y": float(point["y"]),
                "x_in": float(point.get("x_in", 0.0)),
                "y_in": float(point.get("y_in", 0.0)),
                "x_out": float(point.get("x_out", 0.0)),
                "y_out": float(point.get("y_out", 0.0)),
                "interp": int(point.get("interp", 0)),
            }
            for point in (keyframes_ba.get("keyframes") or [])
        ]
    entries = keyframes_ba.get("entries") if isinstance(keyframes_ba, dict) else None
    if not isinstance(entries, dict):
        return None
    points: list[dict[str, float | int]] = []
    for key in sorted(entries, key=lambda value: int(value)):
        point_entries = entries[key]["decoded"]["entries"]
        points.append(
            {
                "x": float(point_entries["X"]),
                "y": float(point_entries["Y"]),
                "x_in": float(point_entries["XIn"]),
                "y_in": float(point_entries["YIn"]),
                "x_out": float(point_entries["XOut"]),
                "y_out": float(point_entries["YOut"]),
                "interp": int(point_entries["interp"]),
            }
        )
    return points


def _fairlight_timemap_points_match(actual: list[dict[str, float | int]] | None, expected: list[dict[str, Any]] | None) -> bool:
    if actual is None or expected is None or len(actual) != len(expected):
        return False
    for actual_point, expected_point in zip(actual, expected):
        for field in ("x", "y", "x_in", "y_in", "x_out", "y_out"):
            if abs(float(actual_point[field]) - float(expected_point[field])) > 1e-7:
                return False
        if int(actual_point["interp"]) != int(expected_point.get("interp", 0)):
            return False
    return True


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _resolve_fairlight_elastic_audio_selection(
    conn: Any,
    *,
    clip: str | None,
    at: str | None,
    timeline_name: str | None,
) -> dict[str, db_timeline_selection.LiveItemRef]:
    clip_text = str(clip or "").strip()
    if clip_text:
        try:
            current_database = db_session.resolve_current_disk_project_db(
                conn,
                allow_project_name_inference=True,
            )
            connection = sqlite3.connect(f"file:{current_database['project_db_path']}?mode=ro", uri=True, timeout=2.0)
            connection.row_factory = sqlite3.Row
            try:
                cursor = connection.cursor()
                id_matches: list[db_timeline_selection.LiveItemRef] = []
                available_audio_items: list[dict[str, Any]] = []
                for item in db_timeline_selection._read_live_items(conn, track_type="audio"):  # type: ignore[attr-defined]
                    try:
                        row = db_timeline_rows.find_ti_item_row(
                            cursor,
                            item=item,
                            db_type="Sm2TiAudioClip",
                            timeline_name=timeline_name,
                        )
                    except Exception:
                        continue
                    item_id = str(row.get("Sm2TiItem_id") or "")
                    available_audio_items.append(
                        {
                            "clip_id": item_id,
                            "name": row.get("Name") or item.name,
                            "track_index": item.track_index,
                            "start": item.start,
                            "duration": item.duration,
                        }
                    )
                    if item_id == clip_text:
                        id_matches.append(item)
            finally:
                connection.close()
            if id_matches:
                if at:
                    record_frame = db_timeline_selection.resolve_record_frame(conn, at=at)
                    id_matches = db_timeline_selection._filter_items_covering_frame(  # type: ignore[attr-defined]
                        conn,
                        items=id_matches,
                        record_frame=record_frame,
                    )
                if len(id_matches) == 1:
                    return {"audio": id_matches[0]}
                if len(id_matches) > 1:
                    raise ValidationError(
                        "Audio clip item id selection is ambiguous.",
                        details={"clip": clip_text, "at": at, "matches": [item.__dict__ for item in id_matches]},
                        recoverability="not_applicable",
                    )
                raise ReadinessFailed(
                    "Audio clip item id does not cover the requested --at position.",
                    details={"clip": clip_text, "at": at, "available_audio_items": available_audio_items[:20]},
                    recoverability="manual",
                )
            if _looks_like_uuid(clip_text):
                raise ClipNotFound(
                    f"Audio clip item id '{clip_text}' not found on timeline.",
                    details={"clip": clip_text, "track_type": "audio", "available_audio_items": available_audio_items[:20]},
                )
        except (ValidationError, ReadinessFailed, ClipNotFound):
            raise
        except Exception:
            pass
    return db_timeline_selection.resolve_audio_group(conn, clip_name=clip, at=at)


def _verify_fairlight_elastic_segment_timemap(fresh_conn: Any, mutation_result: dict[str, Any], session: Any) -> dict[str, Any]:
    connection = sqlite3.connect(session.project_db_path, timeout=2.0)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT Sm2TiItem_id, Name, Start, Duration, MediaTimemapBA FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
            (mutation_result["item_id"],),
        ).fetchone()
        raw_timemap = bytes(row["MediaTimemapBA"] or b"") if row else b""
        decoded_points = _fairlight_decoded_timemap_points(raw_timemap) if row else None
    finally:
        connection.close()
    expected_points = (mutation_result.get("new_timemap") or {}).get("keyframes")
    duration_ok = row is not None and str(row["Duration"]) == str(mutation_result["new_duration"])
    timemap_points_match = _fairlight_timemap_points_match(decoded_points, expected_points)
    live_present = None
    try:
        items = fresh_conn.timeline.GetItemListInTrack(str(mutation_result["track_type"]), int(mutation_result["track_index"])) or []
        live_present = any(
            str(item.GetName() or "") == str(mutation_result["name"])
            and int(item.GetStart()) == int(mutation_result["start"])
            for item in items
        )
    except Exception:
        live_present = None
    checks = {
        "row_present": row is not None,
        "duration_ok": bool(duration_ok),
        "timemap_non_default": bool(raw_timemap) and not (len(raw_timemap) == 9 and raw_timemap[:1] == b"\x02"),
        "decoded_point_count": len(decoded_points or []),
        "timemap_points_match": bool(timemap_points_match),
        "live_item_present_after_reopen": live_present,
        "actual_points": decoded_points,
        "expected_points": expected_points,
    }
    if not (checks["row_present"] and checks["duration_ok"] and checks["timemap_non_default"] and checks["timemap_points_match"] and live_present is not False):
        raise APICallFailed(
            "Fairlight Elastic segment timemap verification failed after project reopen.",
            details={"checks": checks, "updated": mutation_result},
            recoverability="manual",
        )
    return {"status": "verified", "checks": checks}


elastic_app = typer.Typer(help="Fairlight Elastic Wave operations.")
app.add_typer(elastic_app, name="elastic")


_FAIRLIGHT_ELASTIC_DB_BLOCKER_EVIDENCE = {
    "available_db_route": (
        "`fairlight elastic info` reads stored speed/profile/retime candidates plus clip-level "
        "`Sm2TiItem.FieldsBlob.FL::Retimer` state. `fairlight elastic enable --algorithm voice|general-purpose|varispeed` "
        "can set live-verified Elastic Wave algorithm payloads. `fairlight elastic keyframe --ratio` can apply a whole-clip "
        "audio stretch through the native `Sm2TiItem.MediaTimemapBA` retime storage. "
        "`fairlight elastic keyframe --time-point x=OUTPUT,y=SOURCE` can apply verified explicit segment timemap "
        "points plus raw `x_in/y_in/x_out/y_out/interp` handle values. A DaVinci Resolve GUI Cmd-click timing-point "
        "audit wrote the same `MediaTimemapBA`/`RetimeKeyframeListProto` model; direct pitch-preservation "
        "storage flags remain unmapped."
    ),
    "db_readback_command": "cutagent fairlight elastic info --json",
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "negative_elastic_wave_schema_probe",
        "searched_table_or_column_fragments": [
            "elastic",
            "wave",
            "stretch",
            "pitch",
            "retime",
            "speed",
        ],
        "retime_storage_tables_seen": [
            "SM_Clip",
            "SM_Setup",
            "SmSpeedProfile",
        ],
        "retime_storage_columns_seen": [
            "SM_Clip.SpeedProfile",
            "SM_Clip.IsNormalSpeed",
            "SM_Setup.RetimeProcess",
            "SmSpeedProfile.SpeedPercent",
            "SmSpeedProfile.SpeedValue",
            "SmSpeedProfile.IsVariableSpeed",
            "SmSpeedProfile.SpeedCurveParameterBody",
        ],
        "sampled_tables_matching_elastic_wave": [],
        "elastic_specific_columns_seen": ["Sm2TiItem.FieldsBlob.FL::Retimer"],
        "sound_library_wave_columns_seen": [
            "FLAssetBaseClip.ed_wave",
            "FLAssetBaseClip.ed_wave2",
        ],
        "elastic_wave_state_column_found_in_samples": True,
        "elastic_keyframe_schema_found_in_samples": True,
        "gui_authored_timing_point_storage_verified": True,
        "pitch_preserving_stretch_route_found_in_samples": False,
        "pitch_preserving_render_proof_available": True,
    },
    "elastic_model_evidence": {
        "db_tables": [
            "SM_Clip",
            "SmSpeedProfile",
            "SM_Setup",
            "Sm2TiItem",
        ],
        "read_scope": "speed_profile_retime_candidates_clip_level_fl_retimer_and_media_timemap",
        "elastic_wave_state_supported": True,
        "elastic_keyframe_read_supported": True,
        "elastic_enable_supported": True,
        "elastic_keyframe_write_supported": True,
        "whole_clip_stretch_supported": True,
        "explicit_segment_timemap_supported": True,
        "explicit_timemap_handle_read_supported": True,
        "explicit_timemap_handle_write_supported": True,
        "whole_clip_pitch_preservation_render_verified": True,
        "segment_timing_render_verified": True,
        "set_supported": True,
        "verified_write_scope": [
            "Elastic Wave Voice, General Purpose, and Varispeed enable on an audio clip",
            "Sm2TiItem.FieldsBlob.FL::Retimer readback after project reopen",
            "Whole-clip audio stretch through Sm2TiItem.MediaTimemapBA",
            "Explicit segment audio time-point mapping through Sm2TiItem.MediaTimemapBA",
            "Explicit raw timemap handle/interp mapping through Sm2TiItem.MediaTimemapBA",
            "GUI-authored Cmd-click timing-point insertion stored as the same Sm2TiItem.MediaTimemapBA model",
        ],
        "unverified_write_scope": [
            "pitch-preservation storage flag readback",
            "GUI Clear Timing Points removal command was not promoted because the local menu click probe was not stable",
        ],
    },
    "native_probe_evidence": _FAIRLIGHT_ELASTIC_NATIVE_PROBE_EVIDENCE,
    "db_blocker_note": (
        "The clip-level FL::Retimer Voice/General Purpose/Varispeed enable routes, whole-clip MediaTimemapBA "
        "stretch route, explicit segment MediaTimemapBA point route, and explicit raw handle/interp route are "
        "verified. A GUI-authored timing point uses the same MediaTimemapBA storage model. Storage-level "
        "pitch-preservation flags remain residual."
    ),
}


@elastic_app.command("info")
@handle_errors
def elastic_info(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum speed/retime storage rows per table to read"),
):
    """Read stored speed/retime profile candidates for Fairlight Elastic Wave research."""
    enforce_mutation_policy("fairlight.elastic_wave_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.elastic.info",
                "dry_run": True,
                "limit": int(limit),
                "runtime_read_called": False,
                "route": "db_workaround",
                "target": "current_project_speed_retime_storage",
                "read_scope": "speed_profile_retime_candidates_clip_level_fl_retimer_and_media_timemap",
                "elastic_wave_state_supported": True,
                "elastic_keyframe_read_supported": True,
                "elastic_timemap_point_read_supported": True,
                "explicit_timemap_handle_read_supported": True,
                "elastic_enable_supported": True,
                "elastic_keyframe_write_supported": True,
                "explicit_segment_timemap_supported": True,
                "explicit_timemap_handle_write_supported": True,
                "supported_algorithms": ["general_purpose", "varispeed", "voice"],
                "preflight_command": "cutagent fairlight elastic info --json",
            },
            title="Fairlight Elastic Info Plan",
        )
        return
    conn = get_connection(require_project=True, require_timeline=False)
    data = fairlight_ops.read_fairlight_elastic_info_db(conn, limit=limit)
    output(data, title="Fairlight Elastic Info")


@elastic_app.command("enable")
@handle_errors
def elastic_enable(
    clip: str | None = typer.Option(None, "--clip", help="Timeline clip name or item id"),
    enable: bool = typer.Option(True, "--enable/--disable", help="Requested Elastic Wave state"),
    algorithm: str = typer.Option(
        "voice",
        "--algorithm",
        help="Elastic Wave algorithm to enable; live-verified: voice, general-purpose, varispeed",
    ),
):
    """Set the verified clip-level Fairlight Elastic Wave enable state."""
    enforce_mutation_policy("fairlight.elastic_wave_enable", intended_engine="db_workaround", mutating=not is_dry_run())
    set_execution_engine("db_workaround")
    if not clip or not str(clip).strip():
        raise ValidationError("--clip is required for Fairlight Elastic Wave enable/disable.", details={"clip": clip})
    normalized_algorithm = str(algorithm or "voice").strip().casefold().replace("-", "_").replace(" ", "_")
    supported_algorithms = ["general_purpose", "varispeed", "voice"]
    if normalized_algorithm not in supported_algorithms:
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise ValidationError(
            "Unsupported Elastic Wave algorithm.",
            details={
                "algorithm": algorithm,
                "normalized_algorithm": normalized_algorithm,
                "supported_algorithms": supported_algorithms,
                "unsupported_reason": "Supported algorithms must be live-mapped DaVinci Resolve FL::Retimer payloads.",
            },
            recoverability="not_applicable",
        )
    requested = {"clip": clip, "enable": bool(enable), "algorithm": normalized_algorithm}
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.elastic.enable",
                "dry_run": True,
                "runtime_read_called": False,
                "route": "db_workaround",
                "db_table": "Sm2TiItem",
                "db_field": "FieldsBlob",
                "db_payload": "FL::Retimer",
                "requested": requested,
                "elastic_wave_state_supported": True,
                "elastic_enable_supported": True,
                "elastic_keyframe_write_supported": True,
                "explicit_segment_timemap_supported": True,
                "supported_algorithms": supported_algorithms,
                "residual_blockers": ["pitch-preservation storage flag readback"],
            },
            title="Fairlight Elastic Enable Plan",
        )
        return
    conn = get_connection(require_project=True, require_timeline=True)
    data = fairlight_ops.set_fairlight_elastic_wave_db(
        conn,
        clip=str(clip),
        enabled=bool(enable),
        algorithm=normalized_algorithm,
    )
    output(data, title="Fairlight Elastic Enable")


@elastic_app.command("keyframe")
@handle_errors
def elastic_keyframe(
    clip: str | None = typer.Option(None, "--clip", help="Timeline clip name or item id"),
    at: str | None = typer.Option(None, "--at", help="Timeline timecode/frame/seconds for clip selection"),
    ratio: float | None = typer.Option(None, "--ratio", help="Requested whole-clip stretch ratio; 1.25 lengthens by 25%"),
    time_point: list[str] = typer.Option(
        [],
        "--time-point",
        "--point",
        help=(
            "Explicit segment Elastic output-to-source point, e.g. x=5s,y=4s; optional "
            "x_in/y_in/x_out/y_out/interp raw handle fields; repeatable."
        ),
    ),
):
    """Apply verified whole-clip or explicit segment audio stretch."""
    time_point_values = [] if isinstance(time_point, typer.models.OptionInfo) else list(time_point or [])
    requested = {"clip": clip, "at": at, "ratio": ratio, "time_points": time_point_values}
    if ratio is not None and time_point_values:
        raise ValidationError(
            "Use either --ratio for whole-clip stretch or --time-point for segment mapping, not both.",
            details={"ratio": ratio, "time_points": time_point_values},
            recoverability="not_applicable",
        )
    if ratio is None and not time_point_values:
        set_execution_engine("not_available")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise ValidationError(
            "Fairlight Elastic keyframe requires either --ratio or --time-point.",
            details={
                "requested": requested,
                "supported_routes": [
                    "whole_clip_audio_stretch_timemap",
                    "segment_audio_stretch_timemap",
                    "explicit_timemap_handle_write",
                ],
                "usage": (
                    "Use --ratio for whole-clip audio stretch, or --time-point x=OUTPUT,y=SOURCE "
                    "with optional x_in/y_in/x_out/y_out/interp fields for explicit timing points."
                ),
                "evidence": _FAIRLIGHT_ELASTIC_DB_BLOCKER_EVIDENCE,
            },
            recoverability="not_applicable",
        )
    if time_point_values:
        enforce_mutation_policy("fairlight.elastic_wave", intended_engine="db_workaround", mutating=not is_dry_run())
        set_execution_engine("db_workaround")
        set_recoverability("not_applicable")
        if is_dry_run():
            set_verification_status("not_requested")
            output(
                {
                    "action": "fairlight.elastic.keyframe",
                    "dry_run": True,
                    "runtime_read_called": False,
                    "runtime_write_called": False,
                    "route": "db_workaround",
                    "requested": requested,
                    "db_table": "Sm2TiItem",
                    "db_fields": ["Duration", "MediaTimemapBA"],
                    "set_scope": "segment_audio_stretch_timemap",
                    "point_format": (
                        "x=OUTPUT_TIME,y=SOURCE_TIME with optional x_in/y_in/x_out/y_out/interp; "
                        "time values accept s/f/timecode units"
                    ),
                    "pitch_preservation": {
                        "requested": True,
                        "storage_verification": "storage_flag_unavailable",
                        "render_proof": "verified_live_click_timing_fixture",
                    },
                    "whole_clip_stretch_supported": True,
                    "elastic_segment_timemap_supported": True,
                    "explicit_timemap_handle_write_supported": True,
                    "residual_blockers": ["pitch-preservation storage flag readback"],
                    "preflight_command": (
                        "cutagent fairlight elastic keyframe --clip CLIP "
                        "--time-point x=5s,y=4s --json"
                    ),
                },
                title="Fairlight Elastic Segment Plan",
            )
            return
        conn = get_connection(require_project=True, require_timeline=True)
        timeline_name = _current_timeline_name(conn)
        timeline_fps = clip_speed_db.resolve_timeline_fps(conn)
        selection = _resolve_fairlight_elastic_audio_selection(conn, clip=clip, at=at, timeline_name=timeline_name)
        audio_item = selection.get("audio")
        if not isinstance(audio_item, db_timeline_selection.LiveItemRef):
            raise ValidationError(
                "Fairlight Elastic segment mapping requires a resolvable audio timeline item.",
                details={"clip": clip, "at": at},
                recoverability="not_applicable",
            )
        parsed_points = speed_ramp_db.parse_timemap_point_specs(time_point_values, fps=timeline_fps, field="time_point")
        timemap = _build_fairlight_elastic_segment_timemap(
            duration_frames=int(audio_item.duration),
            fps=timeline_fps,
            points=parsed_points or (),
        )

        def _writer(_connection, cursor, _session):
            row = db_timeline_rows.find_ti_item_row(
                cursor,
                item=audio_item,
                db_type="Sm2TiAudioClip",
                timeline_name=timeline_name,
            )
            old_timemap = bytes(row["MediaTimemapBA"] or b"")
            db_timeline_rows.update_row(
                cursor,
                "Sm2TiItem",
                "Sm2TiItem_id",
                row["Sm2TiItem_id"],
                {
                    "MediaTimemapBA": sqlite3.Binary(timemap.media_timemap_ba),
                    "Duration": str(timemap.output_duration_frames),
                },
            )
            return {
                "operation": "fairlight-elastic-segment-timemap",
                "timeline_name": timeline_name,
                "item_id": row["Sm2TiItem_id"],
                "name": row["Name"],
                "track_type": audio_item.track_type,
                "track_index": audio_item.track_index,
                "start": audio_item.start,
                "old_duration": audio_item.duration,
                "new_duration": timemap.output_duration_frames,
                "old_timemap": retime_db.timemap_blob_summary(old_timemap),
                "new_timemap": timemap.to_plan(include_hex=False),
            }

        data = db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="Fairlight Elastic Wave segment audio stretch",
            writer=_writer,
            verifier=_verify_fairlight_elastic_segment_timemap,
            allow_project_name_inference=True,
        )
        data.update(
            {
                "action": "fairlight.elastic.keyframe",
                "timeline_fps": timeline_fps,
                "route": "db_workaround",
                "requested": requested,
                "set_scope": "segment_audio_stretch_timemap",
                "pitch_preservation": {
                    "requested": True,
                    "storage_verification": "storage_flag_unavailable",
                    "render_proof": "verified_live_click_timing_fixture",
                },
                "whole_clip_stretch_supported": True,
                "elastic_segment_timemap_supported": True,
                "elastic_keyframe_write_supported": True,
                "explicit_timemap_handle_write_supported": True,
                "residual_blockers": ["pitch-preservation storage flag readback"],
            }
        )
        output(data, title="Fairlight Elastic Segment")
        return
    stretch_ratio = float(ratio)
    if not math.isfinite(stretch_ratio) or stretch_ratio <= 0:
        raise ValidationError(
            "--ratio must be a finite number greater than 0.",
            details={"ratio": ratio},
            recoverability="not_applicable",
        )
    speed_multiplier = 1.0 / stretch_ratio
    options = clip_speed_db.validate_speed_controls(
        multiplier=speed_multiplier,
        pitch_correction=True,
        keyframes="stretch-to-fit",
    )
    enforce_mutation_policy("fairlight.elastic_wave", intended_engine="db_workaround", mutating=not is_dry_run())
    set_execution_engine("db_workaround")
    set_recoverability("not_applicable")
    if is_dry_run():
        set_verification_status("not_requested")
        output(
            {
                "action": "fairlight.elastic.keyframe",
                "dry_run": True,
                "runtime_read_called": False,
                "runtime_write_called": False,
                "route": "db_workaround",
                "requested": requested,
                "stretch_ratio": stretch_ratio,
                "speed_multiplier": speed_multiplier,
                "db_table": "Sm2TiItem",
                "db_fields": ["Duration", "MediaTimemapBA", "EffectFiltersBA"],
                "set_scope": "whole_clip_audio_stretch_timemap",
                "pitch_preservation": {
                    "requested": True,
                    "storage_verification": "storage_flag_unavailable",
                    "render_proof": "verified_live_440hz_tone_fixture",
                },
                "whole_clip_stretch_supported": True,
                "elastic_keyframe_write_supported": True,
                "explicit_segment_timemap_supported": True,
                "residual_blockers": ["pitch-preservation storage flag readback"],
                "preflight_command": "cutagent fairlight elastic keyframe --clip CLIP --ratio RATIO --json",
            },
            title="Fairlight Elastic Stretch Plan",
        )
        return
    conn = get_connection(require_project=True, require_timeline=True)
    timeline_name = _current_timeline_name(conn)
    timeline_fps = clip_speed_db.resolve_timeline_fps(conn)
    selection = _resolve_fairlight_elastic_audio_selection(conn, clip=clip, at=at, timeline_name=timeline_name)

    def _writer(_connection, cursor, _session):
        result = clip_speed_db.apply_clip_speed(
            cursor,
            conn=conn,
            selection=selection,
            timeline_name=timeline_name,
            options={**options, "ripple_timeline": False},
            fps=timeline_fps,
        )
        return {
            **result,
            "action": "fairlight.elastic.keyframe",
            "route": "db_workaround",
            "requested": requested,
            "stretch_ratio": stretch_ratio,
            "set_scope": "whole_clip_audio_stretch_timemap",
            "pitch_preservation": {
                "requested": True,
                "storage_verification": "reported_per_clip_in_updated.pitch_correction",
                "render_proof": "verified_live_440hz_tone_fixture",
            },
            "whole_clip_stretch_supported": True,
            "elastic_keyframe_write_supported": True,
            "explicit_segment_timemap_supported": True,
            "residual_blockers": ["pitch-preservation storage flag readback"],
        }

    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight Elastic Wave whole-clip audio stretch",
        writer=_writer,
        verifier=clip_speed_db.verify_clip_speed_mutation,
        allow_project_name_inference=True,
    )
    data["timeline_fps"] = timeline_fps
    output(data, title="Fairlight Elastic Stretch")


send_app = typer.Typer(help="Fairlight send operations.")
app.add_typer(send_app, name="send")


_FAIRLIGHT_SEND_SET_DB_BLOCKER_EVIDENCE = {
    "available_db_route": (
        "`fairlight send list` reads stored send/aux-related tokens and candidate bus destinations from "
        "`Sm2Sequence.FieldsBlob.FLStudioModelBA`, but this is a read-only token probe and not a verified "
        "per-track send slot state or mutation route."
    ),
    "db_readback_command": "cutagent fairlight send list --include-context --json",
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "negative_send_slot_schema_probe",
        "searched_table_or_column_fragments": [
            "send",
            "aux",
            "bus",
            "routing",
            "fader",
            "mute",
            "pre_post",
        ],
        "mixer_model_blob_read_by_command": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "token_families_read_by_command": [
            "send",
            "aux",
            "pre-fader",
            "post-fader",
            "bus labels",
        ],
        "sampled_aux_like_schema_entries": [
            "Sm2Sequence.AuxRenderCacheBA",
            "Sm2Sequence.pAuxLmVerTable",
            "Sm2TiItem.pAuxLmVerTable",
        ],
        "sampled_non_send_audio_setup_entries": [
            "SM_UserSetup.MuteAudio",
        ],
        "candidate_destinations_are_bus_labels": True,
        "per_track_send_slot_table_found_in_samples": False,
        "slot_indexed_assignment_schema_found_in_samples": False,
        "send_level_pan_prepost_schema_found_in_samples": False,
        "send_mute_bypass_schema_found_in_samples": False,
        "send_write_readback_route_found_in_samples": False,
    },
    "send_model_evidence": {
        "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "read_scope": "send_token_probe_and_bus_destinations",
        "token_probe_supported": True,
        "candidate_destinations_supported": True,
        "context_supported": True,
        "slot_state_read_supported": False,
        "assignment_supported": False,
        "level_set_supported": False,
        "pan_set_supported": False,
        "pre_post_set_supported": False,
        "mute_set_supported": False,
        "set_supported": False,
        "unverified_write_scope": [
            "per-track send slot assignment",
            "send destination routing",
            "send level",
            "send pan",
            "send pre/post-fader state",
            "send mute/bypass state",
        ],
    },
    "native_probe_evidence": {
        "runtime": "DaVinci Resolve 20.3.2.9 Free",
        "transport": "embedded_lua_http_poll",
        "probe_project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
        "candidate_methods_not_available": [
            "Timeline.GetTrackSendList('audio', 1)",
        ],
        "mutating_candidates_not_called": [
            "Timeline.SetTrackSend('audio', 1, ...)",
        ],
        "resolve_21_embedded_recheck": {
            "runtime": "DaVinci Resolve 21.0.0.48 Free",
            "transport": "embedded_lua_http_poll",
            "artifact": "/tmp/cutagent_send_group_vca_co_20260619/08_direct_send_group_vca_probe_after_allowlist.json",
            "candidate_methods_not_available": [
                "Timeline.GetTrackSendList('audio', 1)",
                "Timeline.GetTrackSends('audio', 1)",
                "Timeline.GetFairlightSends()",
                "Timeline.GetSendList()",
            ],
            "unsupported_bridge_count": 0,
            "probe_result": "send getter candidates reached DaVinci Resolve and returned method_not_available",
        },
        "probe_result": "send slot getter returned method_not_available; mutating send candidate was not called",
        "slot_state_native_read_supported": False,
        "send_mutation_native_supported": False,
    },
    "db_blocker_note": (
        "Candidate bus destinations are timeline bus labels, not proof of active send slots. Send tokens are "
        "diagnostic candidates only until a slot-indexed readback and write model is verified."
    ),
}
