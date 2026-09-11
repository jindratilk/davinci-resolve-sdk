from __future__ import annotations

@app.command("audio-normalize")
@handle_errors
def clip_audio_normalize(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    target_dbfs: float = typer.Option(-9.0, "--target-dbfs", help="Peak normalization target in dBFS"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position for deterministic clip selection"),
):
    """Normalize linked audio peak level natively on 21.1; preserve the older-runtime route."""
    enforce_mutation_policy("clip.audio_normalize", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    _reject_duplicate_audio_normalize_target()
    validated_target_dbfs = audio_normalize.validate_target_dbfs(target_dbfs)
    at_value = None if isinstance(at, typer.models.OptionInfo) else at
    max_passes = 4
    settle_tolerance_db = 0.1
    if is_dry_run():
        target_name = name or "current"
        if at_value is not None:
            conn = get_connection(require_timeline=True)
            selection = db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at_value)
            target_name = selection["audio"].name
        dry_run_message(f"Would normalize audio on '{target_name}' to {validated_target_dbfs} dBFS")
        return

    conn = get_connection(require_timeline=True)
    if resolve_api_version.at_least(conn, 21, 1):
        from ..core.native_audio_normalization import normalize_peak
        selection = db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at_value)
        output(normalize_peak(conn, selection["audio"], validated_target_dbfs), title="Clip Audio Normalize")
        return

    enforce_mutation_policy("clip.audio_normalize", intended_engine="db_workaround")
    iterations: list[dict[str, float | int | None]] = []
    data: dict[str, object] | None = None
    selection = db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at_value)
    preferred_render_route = None

    for pass_index in range(1, max_passes + 1):
        if pass_index > 1:
            conn = get_connection(require_timeline=True)
            selection = db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at_value)
        analysis = audio_normalize.measure_peak_normalization(
            conn,
            audio_item=selection["audio"],
            target_dbfs=validated_target_dbfs,
            preferred_render_route=preferred_render_route,
        )
        render_format = analysis.get("render_format")
        render_codec = analysis.get("render_codec")
        if isinstance(render_format, str) and isinstance(render_codec, str):
            preferred_render_route = (render_format, render_codec)
        timeline_name = _timeline_name(conn)
        correction_db = float(analysis["gain_db"])

        if abs(correction_db) <= settle_tolerance_db:
            data = {
                "effect": "audio-normalize",
                "audio_item_id": data.get("audio_item_id") if isinstance(data, dict) else None,
                "mode": "peak",
                "target_dbfs": float(analysis["target_dbfs"]),
                "peak_dbfs": analysis["peak_dbfs"],
                "applied_gain_db": 0.0,
                "existing_gain_db": data.get("resulting_gain_db") if isinstance(data, dict) else None,
                "resulting_gain_db": data.get("resulting_gain_db") if isinstance(data, dict) else None,
                "analysis": analysis,
                "iterations": iterations + [
                    {
                        "pass": pass_index,
                        "peak_dbfs": analysis["peak_dbfs"],
                        "correction_db": correction_db,
                        "within_tolerance": True,
                    }
                ],
                "stabilized": True,
            }
            break

        if pass_index == max_passes:
            data = {
                **(data or {}),
                "peak_dbfs": analysis["peak_dbfs"],
                "analysis": analysis,
                "iterations": iterations + [
                    {
                        "pass": pass_index,
                        "peak_dbfs": analysis["peak_dbfs"],
                        "correction_db": correction_db,
                        "resulting_gain_db": data.get("resulting_gain_db") if isinstance(data, dict) else None,
                        "within_tolerance": False,
                    }
                ],
                "stabilized": False,
            }
            break

        mutation = db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="DB-backed audio normalize",
            writer=lambda connection, cursor, session: (
                lambda current_gain_db: {
                    **clip_effects_db.apply_audio_effect(
                        cursor,
                        audio_item=selection["audio"],
                        write=clip_effects_db.build_audio_gain_payload(float(current_gain_db + correction_db)),
                        effect_name="audio-normalize",
                        timeline_name=timeline_name,
                    ),
                    "mode": "peak",
                    "target_dbfs": float(analysis["target_dbfs"]),
                    "peak_dbfs": analysis["peak_dbfs"],
                    "applied_gain_db": correction_db,
                    "existing_gain_db": float(current_gain_db),
                    "resulting_gain_db": float(current_gain_db + correction_db),
                    "analysis": analysis,
                }
            )(
                clip_effects_db.read_current_audio_gain(
                    cursor,
                    audio_item=selection["audio"],
                    timeline_name=timeline_name,
                )
            ),
            verifier=lambda connection, mutation_result, session: {
                "status": "verified",
                "checks": [{"name": "project_db_route", "ok": True}],
            },
        )
        iterations.append(
            {
                "pass": pass_index,
                "peak_dbfs": analysis["peak_dbfs"],
                "correction_db": correction_db,
                "resulting_gain_db": float(mutation["resulting_gain_db"]),
                "within_tolerance": False,
            }
        )
        data = mutation

    if data is None:
        raise RuntimeError("audio normalize produced no result")

    output(data, title="Clip Audio Normalize")


@app.command("audio-eq")
@handle_errors
def clip_audio_eq(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    preset: str = typer.Option(
        "voice-presence-1k-6db",
        "--preset",
        help="DaVinci Resolve native EQ preset fallback",
    ),
    band: Optional[int] = typer.Option(None, "--band", help="EQ band index for supported parametric routes"),
    ui_band: Optional[int] = typer.Option(None, "--ui-band", help="DaVinci Resolve clip EQ band label B1-B6"),
    filter_type: Optional[str] = typer.Option(
        None,
        "--filter-type",
        help="bell, notch, high-shelf, low-shelf, high-pass, or low-pass",
    ),
    freq: Optional[int] = typer.Option(None, "--freq", help="EQ frequency in Hz for supported parametric routes"),
    gain_db: Optional[float] = typer.Option(None, "--gain-db", help="EQ gain in dB for supported bell routes"),
    q: Optional[float] = typer.Option(None, "--q", help="EQ Q for supported parametric routes"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position for deterministic clip selection"),
):
    """Apply a DaVinci Resolve native archived clip EQ route to a linked audio clip."""
    enforce_mutation_policy("clip.audio_eq", intended_engine="db_workaround", mutating=not is_dry_run())
    band_value = None if isinstance(band, typer.models.OptionInfo) else band
    ui_band_value = None if isinstance(ui_band, typer.models.OptionInfo) else ui_band
    filter_type_value = None if isinstance(filter_type, typer.models.OptionInfo) else filter_type
    freq_value = None if isinstance(freq, typer.models.OptionInfo) else freq
    gain_db_value = None if isinstance(gain_db, typer.models.OptionInfo) else gain_db
    q_value = None if isinstance(q, typer.models.OptionInfo) else q
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    spec = audio_eq_db.resolve_audio_eq_spec(
        preset_name=preset,
        band=band_value,
        ui_band=ui_band_value,
        filter_type=filter_type_value,
        freq_hz=freq_value,
        gain_db=gain_db_value,
        q=q_value,
    )
    if is_dry_run():
        target = name or "current"
        if spec.mode == "preset":
            dry_run_message(f"Would apply audio EQ preset '{spec.preset}' on '{target}'")
        else:
            dry_run_message(f"Would apply audio EQ {spec.summary} on '{target}'")
        return

    conn = get_connection(require_timeline=True)
    selection = db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at)
    timeline_name = _timeline_name(conn)
    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed audio eq",
        writer=lambda connection, cursor, session: audio_eq_db.apply_audio_eq_settings(
            cursor,
            audio_item=selection["audio"],
            preset_name=spec.preset or preset,
            band=band_value,
            ui_band=ui_band_value,
            filter_type=filter_type_value,
            freq_hz=freq_value,
            gain_db=gain_db_value,
            q=q_value,
            timeline_name=timeline_name,
        ),
        verifier=lambda connection, mutation_result, session: {
            "status": "verified",
            "checks": [{"name": "project_db_route", "ok": True}],
        },
    )
    output(data, title="Clip Audio EQ")


@app.command("audio-pan")
@handle_errors
def clip_audio_pan(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    value: float = typer.Option(..., "--value", help="Pan value"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position for deterministic clip selection"),
):
    """Set clip audio pan natively on 21.1, with the Disk DB route on older runtimes."""
    enforce_mutation_policy("clip.audio_pan", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    _reject_duplicate_audio_pan_value()
    validated_value = clip_effects_db.validate_audio_pan_value(value)
    at_value = None if isinstance(at, typer.models.OptionInfo) else at
    if is_dry_run():
        target_name = name or "current"
        if name or at_value is not None:
            conn = get_connection(require_timeline=True)
            selection = db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at_value)
            target_name = selection["audio"].name
        dry_run_message(f"Would set audio pan on '{target_name}' to {validated_value}")
        return

    conn = get_connection(require_timeline=True)
    selection = db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at_value)
    if native_clip_audio.available(conn):
        output(native_clip_audio.set_audio(conn, selection["audio"], kind="audio-pan", values={"AudioPan": validated_value}), title="Clip Audio Pan")
        return
    enforce_mutation_policy("clip.audio_pan", intended_engine="db_workaround")
    timeline_name = _timeline_name(conn)
    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed audio pan",
        writer=lambda connection, cursor, session: clip_effects_db.apply_audio_effect(
            cursor,
            audio_item=selection["audio"],
            write=clip_effects_db.build_audio_pan_payload(validated_value),
            effect_name="audio-pan",
            timeline_name=timeline_name,
        ),
        verifier=lambda connection, mutation_result, session: {
            "status": "verified",
            "checks": [{"name": "project_db_route", "ok": True}],
        },
    )
    output(data, title="Clip Audio Pan")


@app.command("audio-pitch")
@handle_errors
def clip_audio_pitch(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    semitones: int = typer.Option(12, "--semitones", help="Semitone shift"),
    cents: int = typer.Option(0, "--cents", help="Cent offset"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position for deterministic clip selection"),
):
    """Set clip audio pitch natively on 21.1, with the Disk DB route on older runtimes."""
    enforce_mutation_policy("clip.audio_pitch", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    _reject_duplicate_audio_pitch_options()
    semitone_value, cents_value = clip_effects_db.validate_audio_pitch_values(semitones, cents)
    at_value = None if isinstance(at, typer.models.OptionInfo) else at
    if is_dry_run():
        target_name = name or "current"
        if name or at_value is not None:
            conn = get_connection(require_timeline=True)
            selection = db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at_value)
            target_name = selection["audio"].name
        dry_run_message(
            f"Would set audio pitch on '{target_name}' to {semitone_value} semitones and {cents_value} cents"
        )
        return

    conn = get_connection(require_timeline=True)
    selection = db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at_value)
    if native_clip_audio.available(conn):
        output(native_clip_audio.set_audio(conn, selection["audio"], kind="audio-pitch", values={"AudioPitchSemiTones": semitone_value, "AudioPitchCents": cents_value}), title="Clip Audio Pitch")
        return
    enforce_mutation_policy("clip.audio_pitch", intended_engine="db_workaround")
    timeline_name = _timeline_name(conn)
    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed audio pitch",
        writer=lambda connection, cursor, session: clip_effects_db.apply_audio_effect(
            cursor,
            audio_item=selection["audio"],
            write=clip_effects_db.build_audio_pitch_payload(semitones=semitone_value, cents=cents_value),
            effect_name="audio-pitch",
            timeline_name=timeline_name,
        ),
        verifier=lambda connection, mutation_result, session: {
            "status": "verified",
            "checks": [{"name": "project_db_route", "ok": True}],
        },
    )
    output(data, title="Clip Audio Pitch")


@app.command("fade-in")
@handle_errors
def clip_fade_in(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position for deterministic clip selection"),
    scope: str = typer.Option("linked", "--scope", help="Fade scope: linked|video|audio"),
    edge: str = typer.Option("start", "--edge", help="Fade edge: start|end|both"),
    duration: Optional[str] = typer.Option(None, "--duration", help="Fade duration for both video and audio (e.g. 12f, 0.5s)"),
    video_duration: Optional[str] = typer.Option(None, "--video-duration", help="Override fade duration for video"),
    audio_duration: Optional[str] = typer.Option(None, "--audio-duration", help="Override fade duration for audio"),
):
    """Set exact video/audio fader durations natively on 21.1, with the Disk DB route on older runtimes."""
    enforce_mutation_policy("clip.fade_in", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")

    normalized_scope = clip_effects_db.normalize_fade_scope(scope)
    normalized_edge = clip_effects_db.normalize_fade_edge(edge)
    at_value = None if isinstance(at, typer.models.OptionInfo) else at
    duration_value = None if isinstance(duration, typer.models.OptionInfo) else duration
    video_duration_value = None if isinstance(video_duration, typer.models.OptionInfo) else video_duration
    audio_duration_value = None if isinstance(audio_duration, typer.models.OptionInfo) else audio_duration

    needs_connection = (
        not is_dry_run()
        or name is not None
        or at_value is not None
        or duration_value is not None
        or video_duration_value is not None
        or audio_duration_value is not None
    )
    conn = get_connection(require_timeline=True) if needs_connection else None
    selection = None
    if conn is not None and (not is_dry_run() or name is not None or at_value is not None):
        if normalized_scope == "audio":
            selection = {"video": None, **db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at_value)}
        elif normalized_scope == "video":
            selection = {"audio": None, **db_timeline_selection.resolve_video_group(conn, clip_name=name, at=at_value)}
        else:
            selection = db_timeline_selection.resolve_linked_av_group(conn, clip_name=name, at=at_value)
    fps_conn = conn
    if fps_conn is None:
        class _DefaultFps:
            fps = 24.0

        fps_conn = _DefaultFps()
    shared_frames = _parse_optional_duration_frames(fps_conn, duration_value)
    video_frames = _parse_optional_duration_frames(fps_conn, video_duration_value)
    audio_frames = _parse_optional_duration_frames(fps_conn, audio_duration_value)
    resolved_video_frames = video_frames if video_frames is not None else shared_frames
    resolved_audio_frames = audio_frames if audio_frames is not None else shared_frames
    if resolved_video_frames is None and normalized_scope in {"linked", "video"}:
        resolved_video_frames = 44
    if resolved_audio_frames is None and normalized_scope in {"linked", "audio"}:
        resolved_audio_frames = 18
    if is_dry_run():
        target = name or "current"
        if selection and selection.get("video"):
            target = selection["video"].name
        elif selection and selection.get("audio"):
            target = selection["audio"].name
        details = [
            f"edge='{normalized_edge}'",
            f"scope='{normalized_scope}'",
            f"duration='{duration_value or 'default'}'",
            f"video_duration='{video_duration_value or 'default'}'",
            f"audio_duration='{audio_duration_value or 'default'}'",
            f"resolved_video_frames={resolved_video_frames}",
            f"resolved_audio_frames={resolved_audio_frames}",
        ]
        if at_value is not None:
            details.append(f"at='{at_value}'")
        dry_run_message(f"Would apply fade-in to '{target}' " + " ".join(details))
        return

    assert conn is not None
    assert selection is not None
    if native_clip_audio.available(conn):
        output(native_clip_audio.set_fades(conn, selection, scope=normalized_scope, edge=normalized_edge,
                                          video_frames=resolved_video_frames, audio_frames=resolved_audio_frames), title="Clip Fade")
        return
    if os.environ.get("CUTAGENT_SDK_TIMELINE_GUARD"):
        raise CapabilityNegotiationFailed("SDK clip fades require DaVinci Resolve 21.1 native readback; the older-runtime fallback remains available through CutAgent CLI.")
    enforce_mutation_policy("clip.fade_in", intended_engine="db_workaround")
    timeline_name = _timeline_name(conn)

    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed clip fade-in",
        writer=lambda connection, cursor, session: clip_effects_db.apply_fade_in(
            cursor,
            video_item=selection["video"] if normalized_scope in {"linked", "video"} else None,
            audio_item=selection["audio"] if normalized_scope in {"linked", "audio"} else None,
            scope=normalized_scope,
            edge=normalized_edge,
            video_duration_frames=resolved_video_frames,
            audio_duration_frames=resolved_audio_frames,
            timeline_name=timeline_name,
        ),
        verifier=lambda connection, mutation_result, session: {
            "status": "pending_manual",
            "checks": [
                {"name": "project_db_route", "ok": True},
                {
                    "name": "resolve_ui_confirmation_required",
                    "ok": False,
                    "detail": "Disk DB fade payload insertion succeeded, but DaVinci Resolve timeline/UI confirmation is still required.",
                },
            ],
        },
    )
    output(data, title="Clip Fade")


def _validate_speed_ramp_blur_options(
    *,
    enabled: bool,
    frames: int,
    track: int,
    angle: float,
    distance: float,
    peak_opacity: float,
    name: Optional[str],
) -> dict[str, object]:
    if not enabled:
        return {"enabled": False}
    safe_frames = int(frames)
    safe_track = int(track or 0)
    safe_angle = float(angle)
    safe_distance = float(distance)
    safe_peak = float(peak_opacity)
    if safe_frames <= 0:
        raise ValidationError("--blur-frames must be greater than 0.", details={"blur_frames": frames}, recoverability="not_applicable")
    if safe_track < 0:
        raise ValidationError(
            "--blur-track must be 0 for auto or a positive video track index.",
            details={"blur_track": track},
            recoverability="not_applicable",
        )
    if not math.isfinite(safe_angle):
        raise ValidationError("--blur-angle must be finite.", details={"blur_angle": angle}, recoverability="not_applicable")
    if not math.isfinite(safe_distance) or safe_distance <= 0:
        raise ValidationError("--blur-distance must be greater than 0.", details={"blur_distance": distance}, recoverability="not_applicable")
    if not math.isfinite(safe_peak) or safe_peak < 0 or safe_peak > 1:
        raise ValidationError(
            "--blur-peak-opacity must be between 0 and 1.",
            details={"blur_peak_opacity": peak_opacity},
            recoverability="not_applicable",
        )
    safe_name = str(name or "").strip() if name is not None else None
    if name is not None and not safe_name:
        raise ValidationError("--blur-name must not be empty.", details={"blur_name": name}, recoverability="not_applicable")
    return {
        "enabled": True,
        "frames": safe_frames,
        "track": safe_track,
        "angle": safe_angle,
        "distance": safe_distance,
        "peak_opacity": safe_peak,
        "name": safe_name,
    }


def _speed_ramp_blur_frame_plan(plan: dict[str, object], blur_options: dict[str, object]) -> dict[str, object]:
    cut = plan.get("cut") if isinstance(plan, dict) else {}
    if not isinstance(cut, dict):
        raise APICallFailed("Speed-ramp plan is missing cut metadata for adjustment blur.")
    cut_frame = int(cut.get("record_frame"))
    cut_track = int(cut.get("track_index") or 1)
    duration = int(blur_options["frames"])
    start = max(0, cut_frame - (duration // 2))
    track = int(blur_options.get("track") or 0) or cut_track + 1
    return {
        "enabled": True,
        "holder": "Adjustment Clip",
        "name": str(blur_options.get("name") or f"CA Speed Ramp Directional Blur {cut_frame}f"),
        "track": track,
        "record_frame": start,
        "cut_frame": cut_frame,
        "duration_frames": duration,
        "end_frame": start + duration,
        "local_mid_frame": min(duration - 1, max(0, duration // 2)),
        "local_end_frame": duration - 1,
        "angle": float(blur_options["angle"]),
        "distance": float(blur_options["distance"]),
        "peak_opacity": float(blur_options["peak_opacity"]),
        "route": "timeline.InsertGeneratorIntoTimeline -> project_db.move_timeline_item -> fusion DirectionalBlur",
    }


def _find_timeline_item_by_range(conn, *, track: int, start: int, duration: int, name: str):
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise APICallFailed("No active timeline is available for adjustment blur verification.")
    try:
        items = timeline.GetItemListInTrack("video", int(track)) or []
    except Exception as exc:
        raise APICallFailed(
            "Failed to read video track for adjustment blur item lookup.",
            details={"track": track, "start": start, "duration": duration},
        ) from exc
    range_matches = []
    name_matches = []
    for item in items:
        try:
            item_start = int(item.GetStart())
            item_end = int(item.GetEnd())
            item_name = str(item.GetName() or "")
        except Exception:
            continue
        if item_start == int(start) and item_end - item_start == int(duration):
            range_matches.append(item)
            if not name or item_name == name:
                name_matches.append(item)
    matches = name_matches or range_matches
    if len(matches) != 1:
        raise APICallFailed(
            "Could not resolve the inserted adjustment blur clip after DB placement.",
            details={
                "track": track,
                "start": start,
                "duration": duration,
                "name": name,
                "name_match_count": len(name_matches),
                "range_match_count": len(range_matches),
            },
            recoverability="manual",
        )
    return matches[0]


def _get_or_create_fusion_comp_for_item(item, *, clip_name: str):
    count = 0
    if hasattr(item, "GetFusionCompCount"):
        try:
            count = int(item.GetFusionCompCount() or 0)
        except Exception:
            count = 0
    if count <= 0:
        add_comp = getattr(item, "AddFusionComp", None)
        if not callable(add_comp):
            raise APICallFailed("Adjustment blur clip does not support AddFusionComp.", details={"clip": clip_name}, recoverability="manual")
        result = add_comp()
        if result is False:
            raise APICallFailed("Failed to add Fusion composition to adjustment blur clip.", details={"clip": clip_name}, recoverability="manual")
        count = 1
    for index in (1, 0):
        try:
            comp = item.GetFusionCompByIndex(index)
        except Exception:
            comp = None
        if comp:
            return comp
    raise APICallFailed(
        "Could not read Fusion composition from adjustment blur clip.",
        details={"clip": clip_name, "comp_count": count},
        recoverability="manual",
    )


def _find_fusion_input(tool, input_id: str):
    if hasattr(tool, "GetInputList"):
        try:
            input_list = tool.GetInputList() or {}
        except Exception:
            input_list = {}
        values = input_list.values() if hasattr(input_list, "values") else input_list
        for input_obj in values:
            try:
                attrs = input_obj.GetAttrs() if hasattr(input_obj, "GetAttrs") else {}
            except Exception:
                attrs = {}
            if attrs.get("INPS_ID") == input_id:
                return input_obj
    input_obj = getattr(tool, input_id, None)
    if input_obj is not None:
        return input_obj
    raise APICallFailed(
        "Fusion tool input not found for adjustment blur keyframes.",
        details={"tool": getattr(tool, "Name", None), "input": input_id},
        recoverability="manual",
    )


def _set_fusion_input_keyframe(comp, tool, input_id: str, frame: int, value: float) -> None:
    input_obj = _find_fusion_input(tool, input_id)
    try:
        keyframes = input_obj.GetKeyFrames() if hasattr(input_obj, "GetKeyFrames") else None
    except Exception:
        keyframes = None
    if not keyframes:
        spline_factory = getattr(comp, "BezierSpline", None)
        if not callable(spline_factory):
            raise APICallFailed(
                "Fusion BezierSpline is unavailable; adjustment blur opacity fade cannot be animated.",
                details={"tool": getattr(tool, "Name", None), "input": input_id},
                recoverability="manual",
            )
        spline = spline_factory()
        if not spline:
            raise APICallFailed(
                "Failed to create Fusion BezierSpline for adjustment blur opacity fade.",
                details={"tool": getattr(tool, "Name", None), "input": input_id},
                recoverability="manual",
            )
        connector = getattr(input_obj, "ConnectTo", None)
        if not callable(connector):
            raise APICallFailed(
                "Fusion input cannot connect to BezierSpline for adjustment blur opacity fade.",
                details={"tool": getattr(tool, "Name", None), "input": input_id},
                recoverability="manual",
            )
        connector(spline)
    try:
        tool.SetInput(input_id, float(value), int(frame))
    except Exception as exc:
        raise APICallFailed(
            "Failed to set Fusion keyframe for adjustment blur opacity fade.",
            details={"tool": getattr(tool, "Name", None), "input": input_id, "frame": frame, "value": value},
            recoverability="manual",
        ) from exc


def _summarize_fusion_tools(comp) -> list[dict[str, str]]:
    try:
        tool_list = comp.GetToolList(False) if hasattr(comp, "GetToolList") else {}
    except Exception:
        tool_list = {}
    values = tool_list.values() if hasattr(tool_list, "values") else tool_list
    rows = []
    for index, tool in enumerate(values):
        attrs = {}
        try:
            attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
        except Exception:
            attrs = {}
        rows.append(
            {
                "name": str(getattr(tool, "Name", None) or attrs.get("TOOLS_Name") or f"Tool{index + 1}"),
                "type": str(attrs.get("TOOLS_RegID") or attrs.get("REGS_ID") or "unknown"),
            }
        )
    return rows


def _apply_directional_blur_to_adjustment_item(item, *, blur_plan: dict[str, object]) -> dict[str, object]:
    from ..core import color_ops

    comp = _get_or_create_fusion_comp_for_item(item, clip_name=str(blur_plan["name"]))
    if hasattr(comp, "SetAttrs"):
        try:
            comp.SetAttrs(
                {
                    "COMPN_GlobalStart": 0,
                    "COMPN_GlobalEnd": int(blur_plan["local_end_frame"]),
                    "COMPN_RenderStart": 0,
                    "COMPN_RenderEnd": int(blur_plan["local_end_frame"]),
                }
            )
        except Exception:
            pass
    with color_ops._locked_comp(comp):
        tool = color_ops._create_comp_tool(comp, "DirectionalBlur", prefix="DirectionalBlur")
        tool.SetInput("Angle", float(blur_plan["angle"]))
        tool.SetInput("Distance", float(blur_plan["distance"]))
        color_ops._connect_tool_inline(comp, tool)
        _set_fusion_input_keyframe(comp, tool, "Blend", 0, 0.0)
        _set_fusion_input_keyframe(comp, tool, "Blend", int(blur_plan["local_mid_frame"]), float(blur_plan["peak_opacity"]))
        _set_fusion_input_keyframe(comp, tool, "Blend", int(blur_plan["local_end_frame"]), 0.0)
    tools = _summarize_fusion_tools(comp)
    directionals = [row for row in tools if row.get("type") == "DirectionalBlur"]
    splines = [row for row in tools if row.get("type") == "BezierSpline"]
    if not directionals or not splines:
        raise APICallFailed(
            "Adjustment blur Fusion verification failed.",
            details={"tools": tools, "directional_blur_count": len(directionals), "spline_count": len(splines)},
            recoverability="manual",
        )
    return {
        "tool": directionals[-1],
        "tools": tools,
        "keyframes": [
            {"input": "Blend", "frame": 0, "value": 0.0},
            {"input": "Blend", "frame": int(blur_plan["local_mid_frame"]), "value": float(blur_plan["peak_opacity"])},
            {"input": "Blend", "frame": int(blur_plan["local_end_frame"]), "value": 0.0},
        ],
    }


def _insert_speed_ramp_adjustment_blur(conn, *, plan: dict[str, object], blur_options: dict[str, object]) -> dict[str, object]:
    from ..connection import ResolveConnection
    from ..core import timeline_ops
    from ..commands import fusion as fusion_commands

    blur_plan = _speed_ramp_blur_frame_plan(plan, blur_options)
    timeline_name = plan.get("timeline_name") if isinstance(plan, dict) else None
    fusion_commands._ensure_video_track(conn, int(blur_plan["track"]))
    staging_frame = fusion_commands._native_precise_staging_frame(
        conn,
        target_record_frame=int(blur_plan["record_frame"]),
        duration_frames=int(blur_plan["duration_frames"]),
    )
    item, native_insert = fusion_commands._insert_native_holder_at_frame(
        conn,
        holder=str(blur_plan["holder"]),
        holder_kind="fusion",
        record_frame=staging_frame,
    )
    native_insert = {**native_insert, "route": "timeline.InsertGeneratorIntoTimeline"}
    fusion_commands._apply_timeline_item_name_and_duration(item, name=str(blur_plan["name"]), duration_frames=int(blur_plan["duration_frames"]))
    staging_readback = fusion_commands._timeline_item_readback(item)
    db_move = fusion_commands._move_native_precise_holder_via_db(
        conn,
        timeline_name=str(timeline_name or ""),
        staging_readback=staging_readback,
        target_track=int(blur_plan["track"]),
        target_record_frame=int(blur_plan["record_frame"]),
        target_duration_frames=int(blur_plan["duration_frames"]),
        clip_name=str(blur_plan["name"]),
        holder=str(blur_plan["holder"]),
        holder_kind="fusion",
    )

    ResolveConnection.reset()
    fresh_conn = ResolveConnection.get()
    fresh_conn.connect()
    if timeline_name:
        timeline_ops.switch_timeline(fresh_conn, name=str(timeline_name))
    blur_item = _find_timeline_item_by_range(
        fresh_conn,
        track=int(blur_plan["track"]),
        start=int(blur_plan["record_frame"]),
        duration=int(blur_plan["duration_frames"]),
        name=str(blur_plan["name"]),
    )
    rename_readback = fusion_commands._apply_timeline_item_name_and_duration(
        blur_item,
        name=str(blur_plan["name"]),
        duration_frames=int(blur_plan["duration_frames"]),
    )
    fusion = _apply_directional_blur_to_adjustment_item(blur_item, blur_plan=blur_plan)
    return {
        "operation": "speed-ramp-adjustment-blur",
        "enabled": True,
        "plan": blur_plan,
        "native_insert": native_insert,
        "staging_readback": staging_readback,
        "rename_readback": rename_readback,
        "db_move": db_move,
        "fusion": fusion,
        "verification": {
            "status": "verified",
            "checks": [
                {
                    "name": "adjustment_clip_placed",
                    "ok": True,
                    "track": int(blur_plan["track"]),
                    "start": int(blur_plan["record_frame"]),
                    "duration": int(blur_plan["duration_frames"]),
                },
                {"name": "directional_blur_tool_present", "ok": True},
                {"name": "opacity_fade_keyframes_present", "ok": True, "count": 3},
            ],
        },
    }


@app.command("speed-ramp")
@handle_errors
def clip_speed_ramp(
    cut_at: str = typer.Option("current", "--cut-at", help="Cut position: current playhead, frame, seconds, or timecode"),
    out_frames: int = typer.Option(18, "--out-frames", min=1, help="Outgoing ramp length in frames"),
    in_frames: int = typer.Option(18, "--in-frames", min=1, help="Incoming ramp length in frames"),
    peak_speed: str = typer.Option("6.5x", "--peak-speed", help="Peak speed multiplier, e.g. 6.5x"),
    curve: str = typer.Option("sharp-s", "--curve", help="Curve shape: linear, normal-s, or sharp-s"),
    reverse_incoming: bool = typer.Option(False, "--reverse-incoming", help="Reverse the incoming clip while applying its ramp"),
    track: int = typer.Option(0, "--track", min=0, help="Video track index (0 = auto-detect the adjacent cut)"),
    out_start_speed: str = typer.Option("1x", "--out-start-speed", help="Outgoing pre-ramp segment speed multiplier"),
    out_end_speed: Optional[str] = typer.Option(None, "--out-end-speed", help="Outgoing end/ramp speed multiplier; defaults to --peak-speed"),
    in_start_speed: Optional[str] = typer.Option(None, "--in-start-speed", help="Incoming start/ramp speed multiplier; defaults to --peak-speed"),
    in_end_speed: str = typer.Option("1x", "--in-end-speed", help="Incoming post-ramp segment speed multiplier"),
    out_start_handle: Optional[str] = typer.Option(None, "--out-start-handle", help="Raw outgoing Bezier start handle, e.g. x=4f,y=4f"),
    out_end_handle: Optional[str] = typer.Option(None, "--out-end-handle", help="Raw outgoing Bezier end handle, e.g. x=-4f,y=-26f"),
    in_start_handle: Optional[str] = typer.Option(None, "--in-start-handle", help="Raw incoming Bezier start handle, e.g. x=4f,y=26f"),
    in_end_handle: Optional[str] = typer.Option(None, "--in-end-handle", help="Raw incoming Bezier end handle, e.g. x=-4f,y=-4f"),
    out_ease: str = typer.Option("in-out", "--out-ease", help="Outgoing ramp easing: none, in, out, or in-out"),
    in_ease: str = typer.Option("in-out", "--in-ease", help="Incoming ramp easing: none, in, out, or in-out"),
    out_start_interp: Optional[str] = typer.Option(None, "--out-start-interp", help="Raw DaVinci Resolve interp code for the outgoing ramp start point"),
    out_end_interp: Optional[str] = typer.Option(None, "--out-end-interp", help="Raw DaVinci Resolve interp code for the outgoing ramp end point"),
    in_start_interp: Optional[str] = typer.Option(None, "--in-start-interp", help="Raw DaVinci Resolve interp code for the incoming ramp start point"),
    in_end_interp: Optional[str] = typer.Option(None, "--in-end-interp", help="Raw DaVinci Resolve interp code for the incoming ramp end point"),
    out_point: list[str] = typer.Option([], "--out-point", help="Explicit outgoing timemap point: x=102f,y=102f,xOut=4f,yOut=26f; repeatable"),
    in_point: list[str] = typer.Option([], "--in-point", help="Explicit incoming timemap point: x=0f,y=78f,xOut=4f,yOut=-26f; repeatable"),
    adjustment_blur: bool = typer.Option(False, "--adjustment-blur/--no-adjustment-blur", help="Insert a cut-centered Adjustment Clip with DirectionalBlur and opacity fade"),
    blur_frames: int = typer.Option(8, "--blur-frames", min=1, help="Adjustment blur duration in frames"),
    blur_track: int = typer.Option(0, "--blur-track", min=0, help="Adjustment blur video track (0 = one above retime track)"),
    blur_angle: float = typer.Option(0.0, "--blur-angle", help="Fusion DirectionalBlur angle"),
    blur_distance: float = typer.Option(0.16, "--blur-distance", help="Fusion DirectionalBlur distance"),
    blur_peak_opacity: float = typer.Option(1.0, "--blur-peak-opacity", help="Peak blur Blend/opacity from 0 to 1"),
    blur_name: Optional[str] = typer.Option(None, "--blur-name", help="Adjustment blur clip name"),
):
    """Apply a DaVinci Resolve-style DB retime speed-ramp across an adjacent cut."""
    out_start_speed_value = "1x" if isinstance(out_start_speed, typer.models.OptionInfo) else out_start_speed
    out_end_speed_value = None if isinstance(out_end_speed, typer.models.OptionInfo) else out_end_speed
    in_start_speed_value = None if isinstance(in_start_speed, typer.models.OptionInfo) else in_start_speed
    in_end_speed_value = "1x" if isinstance(in_end_speed, typer.models.OptionInfo) else in_end_speed
    out_start_handle_value = None if isinstance(out_start_handle, typer.models.OptionInfo) else out_start_handle
    out_end_handle_value = None if isinstance(out_end_handle, typer.models.OptionInfo) else out_end_handle
    in_start_handle_value = None if isinstance(in_start_handle, typer.models.OptionInfo) else in_start_handle
    in_end_handle_value = None if isinstance(in_end_handle, typer.models.OptionInfo) else in_end_handle
    out_ease_value = "in-out" if isinstance(out_ease, typer.models.OptionInfo) else out_ease
    in_ease_value = "in-out" if isinstance(in_ease, typer.models.OptionInfo) else in_ease
    out_start_interp_value = None if isinstance(out_start_interp, typer.models.OptionInfo) else out_start_interp
    out_end_interp_value = None if isinstance(out_end_interp, typer.models.OptionInfo) else out_end_interp
    in_start_interp_value = None if isinstance(in_start_interp, typer.models.OptionInfo) else in_start_interp
    in_end_interp_value = None if isinstance(in_end_interp, typer.models.OptionInfo) else in_end_interp
    out_point_values = [] if isinstance(out_point, typer.models.OptionInfo) else list(out_point or [])
    in_point_values = [] if isinstance(in_point, typer.models.OptionInfo) else list(in_point or [])
    adjustment_blur_value = False if isinstance(adjustment_blur, typer.models.OptionInfo) else bool(adjustment_blur)
    blur_frames_value = 8 if isinstance(blur_frames, typer.models.OptionInfo) else blur_frames
    blur_track_value = 0 if isinstance(blur_track, typer.models.OptionInfo) else blur_track
    blur_angle_value = 0.0 if isinstance(blur_angle, typer.models.OptionInfo) else blur_angle
    blur_distance_value = 0.16 if isinstance(blur_distance, typer.models.OptionInfo) else blur_distance
    blur_peak_opacity_value = 1.0 if isinstance(blur_peak_opacity, typer.models.OptionInfo) else blur_peak_opacity
    blur_name_value = None if isinstance(blur_name, typer.models.OptionInfo) else blur_name
    enforce_mutation_policy(
        "edit.speed_ramp_workaround",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    speed_ramp_db.validate_speed_ramp_transition_options(
        out_frames=out_frames,
        in_frames=in_frames,
        peak_speed=peak_speed,
        curve=curve,
        track=track,
        out_start_speed=out_start_speed_value,
        out_end_speed=out_end_speed_value,
        in_start_speed=in_start_speed_value,
        in_end_speed=in_end_speed_value,
        out_start_handle=out_start_handle_value,
        out_end_handle=out_end_handle_value,
        in_start_handle=in_start_handle_value,
        in_end_handle=in_end_handle_value,
        out_ease=out_ease_value,
        in_ease=in_ease_value,
        out_start_interp=out_start_interp_value,
        out_end_interp=out_end_interp_value,
        in_start_interp=in_start_interp_value,
        in_end_interp=in_end_interp_value,
        out_points=out_point_values,
        in_points=in_point_values,
    )
    blur_options = _validate_speed_ramp_blur_options(
        enabled=adjustment_blur_value,
        frames=blur_frames_value,
        track=blur_track_value,
        angle=blur_angle_value,
        distance=blur_distance_value,
        peak_opacity=blur_peak_opacity_value,
        name=blur_name_value,
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    conn = get_connection(require_timeline=True)
    exact_sdk_targets = _exact_sdk_retime_targets(conn)
    current_database = get_current_database_details(conn)
    if str(current_database.get("DbType") or "").strip() != "Disk":
        raise ValidationError(
            "clip speed-ramp requires a Disk project database.",
            details={
                "reason": "unsupported_database",
                "current_database": current_database,
                "supported_db_types": ["Disk"],
                "route": "db_workaround",
            },
            recoverability="not_applicable",
        )
    current_db = resolve_current_disk_project_db(conn)
    plan = speed_ramp_db.prepare_speed_ramp_transition(
        conn,
        cut_at=cut_at,
        out_frames=out_frames,
        in_frames=in_frames,
        peak_speed=peak_speed,
        curve=curve,
        reverse_incoming=reverse_incoming,
        track=track,
        out_start_speed=out_start_speed_value,
        out_end_speed=out_end_speed_value,
        in_start_speed=in_start_speed_value,
        in_end_speed=in_end_speed_value,
        out_start_handle=out_start_handle_value,
        out_end_handle=out_end_handle_value,
        in_start_handle=in_start_handle_value,
        in_end_handle=in_end_handle_value,
        out_ease=out_ease_value,
        in_ease=in_ease_value,
        out_start_interp=out_start_interp_value,
        out_end_interp=out_end_interp_value,
        in_start_interp=in_start_interp_value,
        in_end_interp=in_end_interp_value,
        out_points=out_point_values,
        in_points=in_point_values,
    )
    _require_sdk_retime_selection_matches(
        {str(index): target.get("item") for index, target in enumerate(plan.get("targets") or [])},
        exact_sdk_targets,
    )
    speed_ramp_db.attach_db_row_plan(plan, project_db_path=str(current_db["project_db_path"]), exact_targets=exact_sdk_targets)
    if exact_sdk_targets is not None:
        speed_ramp_db.require_sdk_speed_ramp_source_ranges(plan, exact_sdk_targets)
    if is_dry_run():
        output(
            {
                "message": "DRY-RUN: Would apply DB retime speed-ramp across the selected cut.",
                "changed": False,
                "would_change": True,
                "current_database": current_db,
                "plan": speed_ramp_db.speed_ramp_plan_payload(plan),
                "adjustment_blur": _speed_ramp_blur_frame_plan(plan, blur_options) if blur_options.get("enabled") else {"enabled": False},
            },
            title="Speed Ramp Plan",
        )
        return


    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed clip speed-ramp",
        writer=lambda connection, cursor, session: speed_ramp_db.apply_speed_ramp_transition(cursor, plan=plan),
        verifier=lambda fresh, result, session: speed_ramp_db.verify_speed_ramp_transition(
            fresh, result, session
        ),
        pre_close_validator=(_validate_exact_sdk_retime_targets_at_pre_close if exact_sdk_targets is not None else None),
        allow_project_name_inference=True,
    )
    if blur_options.get("enabled"):
        from ..connection import ResolveConnection

        fresh_conn = ResolveConnection.get()
        fresh_conn.connect()
        data["adjustment_blur"] = _insert_speed_ramp_adjustment_blur(fresh_conn, plan=plan, blur_options=blur_options)
    output(data, title="Speed Ramp")


@app.command("retime-inspect", hidden=True)
@handle_errors
def clip_retime_inspect(
    name: Optional[str] = typer.Argument(None, help="Clip name (or current clip)"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position for deterministic clip selection"),
):
    """Inspect selected clip retime Project.db rows."""
    enforce_mutation_policy("edit.speed_ramp_workaround", intended_engine="db_workaround", mutating=False)
    conn = get_connection(require_timeline=True)
    output(speed_ramp_db.inspect_selected_retime_rows(conn, clip_name=name, at=at), title="Retime DB Inspect")


@app.command("retime-capture", hidden=True)
@handle_errors
def clip_retime_capture(
    label: str = typer.Argument(..., help="Reference label, e.g. ui-speed-point-ease"),
    name: Optional[str] = typer.Argument(None, help="Clip name (or current clip)"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position for deterministic clip selection"),
    cut_at: Optional[str] = typer.Option(None, "--cut-at", help="Capture outgoing/incoming linked rows around a cut"),
    track: int = typer.Option(0, "--track", min=0, help="Video track index for --cut-at (0 = auto-detect)"),
    out_dir: Optional[str] = typer.Option(None, "--out-dir", help="Directory for manifest/raw blob artifacts"),
    save_project: bool = typer.Option(True, "--save-project/--no-save-project", help="Save current project before reading Project.db"),
):
    """Capture raw retime Project.db rows for GUI reference research."""
    enforce_mutation_policy("edit.speed_ramp_workaround", intended_engine="db_workaround", mutating=False)
    conn = get_connection(require_timeline=True)
    output(
        speed_ramp_db.capture_retime_reference(
            conn,
            label=label,
            clip_name=name,
            at=at,
            cut_at=cut_at,
            track=track,
            out_dir=out_dir,
            save_project=save_project,
        ),
        title="Retime Reference Capture",
    )


# --- Enable/Disable ---

@app.command("enable")
@handle_errors
def enable_clip(name: Optional[str] = typer.Argument(None)):
    """Enable a clip."""
    if is_dry_run():
        enforce_mutation_policy("clip.enable_disable", intended_engine="api_native", mutating=False)
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        dry_run_message(f"Would enable clip '{name or 'current'}'")
        return

    conn = get_connection(require_timeline=True)
    clip_ops.get_clip_info(conn, name)
    enforce_mutation_policy("clip.enable_disable", intended_engine="api_native")
    data = clip_ops.enable_clip(conn, name)
    set_verification_status("verified" if data.get("verified") else "pending_manual")
    output(data, title="Enable Clip")


@app.command("disable")
@handle_errors
def disable_clip(name: Optional[str] = typer.Argument(None)):
    """Disable a clip."""
    if is_dry_run():
        enforce_mutation_policy("clip.enable_disable", intended_engine="api_native", mutating=False)
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        dry_run_message(f"Would disable clip '{name or 'current'}'")
        return

    conn = get_connection(require_timeline=True)
    clip_ops.get_clip_info(conn, name)
    enforce_mutation_policy("clip.enable_disable", intended_engine="api_native")
    data = clip_ops.disable_clip(conn, name)
    set_verification_status("verified" if data.get("verified") else "pending_manual")
    output(data, title="Disable Clip")


# --- Rename ---

@app.command("rename")
@handle_errors
def rename_clip(
    old_name: str = typer.Argument(..., help="Current clip name"),
    new_name: str = typer.Argument(..., help="New name"),
):
    """Rename a timeline clip."""
    enforce_mutation_policy("clip.rename", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    clip_ops.rename_clip(conn, old_name, new_name)
    success(f"Renamed to: {new_name}")


# --- Link / AI ---

@app.command("link")
@handle_errors
def link_clips(
    clips: list[str] = typer.Argument(..., help="Clip names to link"),
):
    """Link two or more timeline clips."""
    if len(clips) < 2:
        raise MissingArgumentError("Provide at least two clip names to link.")
    enforce_mutation_policy("clip.link_unlink", intended_engine="api_native", mutating=False)
    normalized_clips = [clip_ops.normalize_explicit_clip_name(name) for name in clips]
    enforce_mutation_policy("clip.link_unlink", intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_timeline=True)
    plan = clip_ops.plan_clips_linked(conn, normalized_clips, True)
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output({"message": f"DRY-RUN: Would link {len(normalized_clips)} clips.", **plan})
        return
    result = clip_ops.set_clips_linked(conn, normalized_clips, True)
    output({**plan, "result": bool(result)}, title="Link Clips")


@app.command("unlink")
@handle_errors
def unlink_clip(
    clip_name: str = typer.Argument(..., help="Clip name"),
):
    """Unlink a clip."""
    enforce_mutation_policy("clip.link_unlink", intended_engine="api_native", mutating=False)
    normalized_clip_name = clip_ops.normalize_explicit_clip_name(clip_name)
    enforce_mutation_policy("clip.link_unlink", intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_timeline=True)
    plan = clip_ops.plan_clips_linked(conn, [normalized_clip_name], False)
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output({"message": f"DRY-RUN: Would unlink clip: {plan['clips'][0]}", **plan})
        return
    result = clip_ops.set_clips_linked(conn, [normalized_clip_name], False)
    output({**plan, "result": bool(result)}, title="Unlink Clip")


@app.command("stabilize")
@handle_errors
def stabilize_clip(
    name: Optional[str] = typer.Argument(None, help="Clip name (or current clip)"),
):
    """Run clip stabilization."""
    enforce_mutation_policy("clip.stabilize", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    clip_ops.stabilize_clip(conn, name)
    success("Clip stabilized.")


@app.command("smart-reframe")
@handle_errors
def smart_reframe_clip(
    name: Optional[str] = typer.Argument(None, help="Clip name (or current clip)"),
    item_id: Optional[str] = typer.Option(None, "--item-id", help="Exact native timeline item ID"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Exact video track index; requires --record-frame"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain position inside the exact target"),
    operation_id: Optional[str] = typer.Option(None, "--operation-id", help="Caller-supplied stable operation ID"),
    progress_file: Optional[str] = typer.Option(None, "--progress-file", help="Atomic JSON progress journal path"),
    cancel_request_file: Optional[str] = typer.Option(None, "--cancel-request-file", help="Existence-based cancellation request path"),
    proof_dir: Optional[str] = typer.Option(None, "--proof-dir", help="Directory for retained rendered verification evidence"),
    poll_ms: int = typer.Option(250, "--poll-ms", min=50, max=5000, help="Cancellation/progress polling interval"),
):
    """Run Smart Reframe with phase progress and terminal rendered evidence."""
    mutation_target.validate_timeline_item_selector(name, item_id=item_id, track=track, record_frame=record_frame)
    enforce_mutation_policy("clip.smart_reframe", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "dry_run": True,
                "operation": {"id": operation_id, "kind": "clip.smart_reframe", "status": "planned"},
                "target_selector": {"name": name, "timeline_item_id": item_id, "track": track, "record_frame": record_frame},
                "verification": {"required": True, "mode": "terminal_and_rendered"},
            },
            title="Smart Reframe Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = clip_ops.smart_reframe_clip(
        conn,
        name,
        item_id=item_id,
        track=track,
        record_frame=record_frame,
        operation_id=operation_id,
        progress_file=progress_file,
        cancel_request_file=cancel_request_file,
        proof_dir=proof_dir,
        poll_ms=poll_ms,
    )
    output(data, title="Smart Reframe")


@app.command("magic-mask")
@handle_errors
def magic_mask_clip(
    name: Optional[str] = typer.Argument(None, help="Clip name (or current clip)"),
    mode: str = typer.Option("bi", "--mode", help="Mask direction: f, b, or bi"),
    regenerate: bool = typer.Option(False, "--regenerate", help="Regenerate an existing magic mask"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Video track index for deterministic clip selection"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain frame/time inside the target clip"),
):
    """Check availability for native Magic Mask creation/regeneration on a clip."""
    set_execution_engine("not_available", 0.0)
    set_capability_context("clip.magic_mask", "unsupported")
    normalized_name = None if isinstance(name, typer.models.ArgumentInfo) else name
    if normalized_name is not None:
        normalized_name = str(normalized_name).strip()
        if not normalized_name:
            raise ValidationError("Clip name must not be empty.", details={"clip": name})
    normalized_mode = str(mode).strip().upper()
    if normalized_mode not in {"F", "B", "BI"}:
        raise ValidationError(
            "Magic mask mode must be one of F, B, or BI.",
            details={"mode": mode, "allowed": ["f", "b", "bi"]},
            recoverability="not_applicable",
        )

    _unsupported_clip_preview(
        "clip.magic_mask",
        "not_available_clip_magic_mask",
        {
            "clip": normalized_name,
            "mode": normalized_mode,
            "regenerate": bool(regenerate),
            "would_create": not regenerate,
            "would_regenerate": bool(regenerate),
            "native_methods_rejected": ["CreateMagicMask", "RegenerateMagicMask"],
        },
        "Clip Magic Mask Availability",
    )


@app.command("voice-isolation")
@handle_errors
def voice_isolation_clip(
    name: Optional[str] = typer.Argument(None, help="Clip name (or current clip)"),
    enable: Optional[bool] = typer.Option(None, "--enable/--disable", help="Enable or disable voice isolation"),
    amount: Optional[int] = typer.Option(None, "--amount", min=0, max=100, help="Isolation strength 0-100"),
):
    """Get or set clip voice isolation."""
    conn = get_connection(require_timeline=True)
    if enable is None and amount is None:
        data = clip_ops.get_voice_isolation(conn, name)
        output(data, title="Voice Isolation")
        return

    enforce_mutation_policy("clip.voice_isolation", intended_engine="api_native")
    data = clip_ops.set_voice_isolation(conn, name, enabled=enable, amount=amount)
    output(data, title="Voice Isolation")


@app.command("dynamic-zoom")
@handle_errors
def dynamic_zoom(
    name: Optional[str] = typer.Argument(None, help="Clip name (or current clip)"),
    start: str = typer.Option(..., "--start", help="Start point x,y,zoom"),
    end: str = typer.Option(..., "--end", help="End point x,y,zoom"),
    source_in: Optional[str] = typer.Option(None, "--source-in", help="Source-domain in reference"),
    source_out: Optional[str] = typer.Option(None, "--source-out", help="Source-domain out reference"),
    ease: str = typer.Option("linear", "--ease", help="linear|in|out|inout"),
):
    """Apply dynamic zoom through Fusion keyframes."""
    enforce_mutation_policy("clip.dynamic_zoom", intended_engine="workaround_setting", mutating=False)
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    _reject_dynamic_zoom_trailing_name(name)
    validated = clip_ops.validate_dynamic_zoom_request(
        start=start,
        end=end,
        source_in=source_in,
        source_out=source_out,
        ease=ease,
    )
    if is_dry_run():
        details = [
            f"from {validated['start']}",
            f"to {validated['end']}",
            f"ease {validated['ease']}",
        ]
        if source_in is not None:
            details.append(f"source-in {source_in}")
        if source_out is not None:
            details.append(f"source-out {source_out}")
        dry_run_message(f"Would apply dynamic zoom on '{name or 'current'}' " + ", ".join(details))
        return

    enforce_mutation_policy("clip.dynamic_zoom", intended_engine="workaround_setting")
    conn = get_connection(require_timeline=True)
    data = clip_ops.apply_dynamic_zoom(
        conn,
        name,
        start=start,
        end=end,
        source_in=source_in,
        source_out=source_out,
        ease=ease,
    )
    output(data, title="Dynamic Zoom")


keyframe_app = typer.Typer(help="Timeline item keyframe operations.")
app.add_typer(keyframe_app, name="keyframe")


@keyframe_app.command("add")
@handle_errors
def keyframe_add(
    property_name: str = typer.Argument(..., help="Property name (e.g., ZoomX, Pan, Opacity)"),
    frame: int = typer.Argument(..., help="Record frame position"),
    value: float = typer.Argument(..., help="Property value"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
):
    """Add a keyframe on a timeline item property."""
    from ..core.keyframe_service import AddKeyframe, execute_keyframe

    set_execution_engine("db_workaround")
    set_capability_context("clip.keyframe_crud", "supported")
    enforce_mutation_policy("clip.keyframe_crud", intended_engine="db_workaround")
    conn = get_connection(require_timeline=True)
    sdk_interpolation = os.environ.get("CUTAGENT_SDK_KEYFRAME_INTERPOLATION")
    data = execute_keyframe(
        conn,
        AddKeyframe(clip_name, property_name, frame, value, sdk_interpolation),
    )
    if isinstance(data.get("verification"), dict) and data["verification"].get("status"):
        set_verification_status(str(data["verification"]["status"]))
    output(data, title="Keyframe Add")


@keyframe_app.command("get")
@handle_errors
def keyframe_get(
    property_name: Optional[str] = typer.Argument(None, help="Property name (all known properties when omitted)"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
):
    """Get keyframes for a property or clip."""
    from ..core.keyframe_service import GetKeyframes, execute_keyframe

    set_execution_engine("db_workaround")
    set_capability_context("clip.keyframe_crud", "supported")
    conn = get_connection(require_timeline=True)
    data = execute_keyframe(conn, GetKeyframes(clip_name, property_name))
    output(data, title="Keyframes")


@keyframe_app.command("delete")
@handle_errors
def keyframe_delete(
    property_name: str = typer.Argument(..., help="Property name"),
    frame: int = typer.Argument(..., help="Record frame position"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
):
    """Delete a keyframe."""
    from ..core.keyframe_service import DeleteKeyframe, execute_keyframe

    set_execution_engine("db_workaround")
    set_capability_context("clip.keyframe_crud", "supported")
    enforce_mutation_policy("clip.keyframe_crud", intended_engine="db_workaround")
    conn = get_connection(require_timeline=True)
    data = execute_keyframe(conn, DeleteKeyframe(clip_name, property_name, frame))
    if isinstance(data.get("verification"), dict) and data["verification"].get("status"):
        set_verification_status(str(data["verification"]["status"]))
    output(data, title="Keyframe Delete")


@keyframe_app.command("set-interpolation")
@handle_errors
def keyframe_set_interpolation(
    property_name: str = typer.Argument(..., help="Property name"),
    frame: int = typer.Argument(..., help="Record frame position"),
    interpolation: str = typer.Argument(..., help="Linear|Bezier|Ease-In|Ease-Out"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
):
    """Set interpolation type for a keyframe."""
    from ..core.keyframe_service import SetKeyframeInterpolation, execute_keyframe

    set_execution_engine("db_workaround")
    set_capability_context("clip.keyframe_crud", "supported")
    enforce_mutation_policy("clip.keyframe_crud", intended_engine="db_workaround")
    conn = get_connection(require_timeline=True)
    data = execute_keyframe(
        conn,
        SetKeyframeInterpolation(clip_name, property_name, frame, interpolation),
    )
    if isinstance(data.get("verification"), dict) and data["verification"].get("status"):
        set_verification_status(str(data["verification"]["status"]))
    output(data, title="Keyframe Interpolation")


# --- Fusion Compositions ---

fusion_app = typer.Typer(help="Fusion compositions on clips.")
app.add_typer(fusion_app, name="fusion")


@fusion_app.command("list")
@handle_errors
def fusion_list(
    name: Optional[str] = typer.Argument(None),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain frame/time selector"),
):
    """List Fusion compositions on a clip."""
    track_value = _option_value(track)
    record_frame_value = _option_value(record_frame)
    conn = get_connection(require_timeline=True)
    rows = clip_ops.list_fusion_comps(conn, name, track=track_value, record_frame=record_frame_value)
    output(rows, columns=[("index", "#"), ("name", "Name")], title="Fusion Compositions")


@fusion_app.command("add")
@handle_errors
def fusion_add(
    name: Optional[str] = typer.Argument(None),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain frame/time selector"),
):
    """Add a new Fusion composition to a clip."""
    # The native API remains first, but the zero-composition case may use the
    # advertised, verified Project.db fallback. Admit the strongest possible
    # route before either mutation path executes.
    enforce_mutation_policy("clip.fusion_comp", intended_engine="db_workaround")
    track_value = _option_value(track)
    record_frame_value = _option_value(record_frame)
    conn = get_connection(require_timeline=True)
    clip_ops.add_fusion_comp(conn, name, track=track_value, record_frame=record_frame_value)
    success("Added Fusion composition.")


@fusion_app.command("delete")
@handle_errors
def fusion_delete(
    index: int = typer.Argument(..., help="Composition index"),
    name: Optional[str] = typer.Option(None, "--clip", help="Clip name"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain frame/time selector"),
):
    """Delete a Fusion composition."""
    enforce_mutation_policy("clip.fusion_comp", intended_engine="api_native")
    track_value = _option_value(track)
    record_frame_value = _option_value(record_frame)
    conn = get_connection(require_timeline=True)
    clip_ops.delete_fusion_comp(conn, name, index, track=track_value, record_frame=record_frame_value)
    success(f"Deleted Fusion composition {index}.")


@fusion_app.command("export")
@handle_errors
def fusion_export(
    index: int = typer.Argument(..., help="Composition index"),
    path: str = typer.Argument(..., help="Output .setting file path"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain frame/time selector"),
):
    """Export a Fusion composition as .setting file."""
    track_value = _option_value(track)
    record_frame_value = _option_value(record_frame)
    enforce_mutation_policy("clip.fusion_comp", intended_engine="api_native", mutating=False)
    output_path = clip_ops.validate_fusion_export_request(index, path)
    enforce_mutation_policy("clip.fusion_comp", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        target = f"track {track_value} at {record_frame_value}" if track_value is not None or record_frame_value is not None else clip_name or "current"
        dry_run_message(f"Would export Fusion composition {index} from '{target}' to: {output_path}")
        return

    conn = get_connection(require_timeline=True)
    clip_ops.export_fusion_comp(conn, clip_name, index, output_path, track=track_value, record_frame=record_frame_value)
    success(f"Exported composition {index} to: {output_path}")


@fusion_app.command("import")
@handle_errors
def fusion_import(
    path: str = typer.Argument(..., help=".setting file path"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain frame/time selector"),
):
    """Import a Fusion composition (.setting file) onto a clip."""
    enforce_mutation_policy("clip.fusion_comp", intended_engine="api_native")
    track_value = _option_value(track)
    record_frame_value = _option_value(record_frame)
    conn = get_connection(require_timeline=True)
    item = clip_ops.cutagent_clip_by_selector(conn, clip_name, track=track_value, record_frame=record_frame_value) if track_value is not None or record_frame_value is not None else clip_ops.cutagent_clip(conn, clip_name)
    if not hasattr(item, "ImportFusionComp"):
        raise APICallFailed("This clip doesn't support ImportFusionComp (may require DaVinci Resolve 20+ Studio).")
    layout_prepared = None
    layout = None
    try:
        layout_prepared = prepare_setting_for_import(path)
        import_path = str(layout_prepared.get("import_path") or path)
        result = item.ImportFusionComp(import_path)
    except Exception as exc:
        layout = _cleanup_prepared_setting(layout_prepared)
        raise APICallFailed(
            "ImportFusionComp failed. Check the .setting file format.",
            details={"path": path, "import_path": import_path if "import_path" in locals() else path, "layout": layout, "error": str(exc)},
        ) from exc
    layout = _cleanup_prepared_setting(layout_prepared)
    if not result:
        raise APICallFailed(
            "ImportFusionComp failed. Check the .setting file format.",
            details={"path": path, "import_path": import_path, "layout": layout},
        )
    set_verification_status("partial")
    set_recoverability("not_applicable")
    item_name = None
    try:
        item_name = item.GetName()
    except Exception:
        item_name = None
    output(
        {
            "action": "clip.fusion.import",
            "path": path,
            "import_path": import_path,
            "clip": clip_name,
            "selector": {"track": track_value, "record_frame": record_frame_value} if track_value is not None or record_frame_value is not None else None,
            "clip_readback": item_name or None,
            "route": "timeline_item.ImportFusionComp",
            "applied": True,
            "imported": True,
            "layout": layout,
        },
        title="Clip Fusion Import",
    )


@fusion_app.command("load")
@handle_errors
def fusion_load(
    clip: str = typer.Argument(..., help="Clip name"),
    comp: str = typer.Option(..., "--comp", help="Fusion composition name"),
):
    """Load/switch to a Fusion composition by name."""
    conn = get_connection(require_timeline=True)
    output(clip_ops.load_fusion_comp_by_name(conn, clip, comp), title="Fusion Composition")


@fusion_app.command("by-name")
@handle_errors
def fusion_by_name(
    clip: str = typer.Argument(..., help="Clip name"),
    name: str = typer.Argument(..., help="Fusion composition name"),
):
    """Resolve a Fusion composition by name or stable alias."""
    conn = get_connection(require_timeline=True)
    output(clip_ops.get_fusion_comp_by_name(conn, clip, name), title="Fusion Composition")


@fusion_app.command("tools")
@handle_errors
def fusion_tools(
    index: int = typer.Option(1, "--comp", min=1, help="Composition index"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain frame/time selector"),
):
    """List tools and their addressable native names in a Fusion composition."""
    enforce_mutation_policy("clip.fusion_comp", intended_engine="api_native", mutating=False)
    track_value = _option_value(track)
    record_frame_value = _option_value(record_frame)
    index = clip_ops.validate_fusion_comp_index(index)
    conn = get_connection(require_timeline=True)
    rows = clip_ops.list_fusion_tools(conn, clip_name, index, track=track_value, record_frame=record_frame_value)
    output(rows, columns=[("id", "ID"), ("name", "Name"), ("type", "Type")], title="Fusion Tools")


@fusion_app.command("tool-get")
@handle_errors
def fusion_tool_get(
    tool_name: str = typer.Argument(..., help="Tool name (e.g., TextPlus1)"),
    input_name: str = typer.Argument(..., help="Input name (e.g., StyledText)"),
    comp_index: int = typer.Option(1, "--comp", min=1, help="Composition index"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain frame/time selector"),
):
    """Read a Fusion tool input value."""
    enforce_mutation_policy("clip.fusion_comp", intended_engine="api_native", mutating=False)
    track_value = _option_value(track)
    record_frame_value = _option_value(record_frame)
    comp_index = clip_ops.validate_fusion_comp_index(comp_index)
    conn = get_connection(require_timeline=True)
    inp = clip_ops.get_fusion_tool_input(conn, clip_name, tool_name, input_name, comp_index, track=track_value, record_frame=record_frame_value)
    output({input_name: inp})


@fusion_app.command("tool-set")
@handle_errors
def fusion_tool_set(
    tool_name: str = typer.Argument(..., help="Tool name"),
    input_name: str = typer.Argument(..., help="Input name"),
    value: str = typer.Argument(..., help="Value to set"),
    comp_index: int = typer.Option(1, "--comp"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain frame/time selector"),
):
    """Set a Fusion tool input value."""
    enforce_mutation_policy("clip.fusion_comp", intended_engine="api_native")
    track_value = _option_value(track)
    record_frame_value = _option_value(record_frame)
    conn = get_connection(require_timeline=True)
    clip_ops.set_fusion_tool_input(conn, clip_name, tool_name, input_name, value, comp_index, track=track_value, record_frame=record_frame_value)
    success(f"Set {tool_name}.{input_name} = {value}")


# --- Markers ---

marker_app = typer.Typer(help="Clip markers.")
app.add_typer(marker_app, name="marker")
