from __future__ import annotations

_AUDIO_CAPABLE_FORMAT_CANDIDATES = (("mov", "H264"), ("mp4", "H264"))
_AUDIO_ONLY_PRESET = "Audio Only"


def _verify_opaque_wave_pcm_job(conn, *, job_id: str, target_dir: str, output_filename: str) -> None:
    jobs = _get_render_jobs_safely(conn)
    matches = [job for job in jobs if str(job.get("JobId") or "") == str(job_id)]
    if len(matches) != 1:
        raise APICallFailed(
            "Cannot bind the preset-backed Wave render job for exact verification.",
            details={"job_id": str(job_id), "match_count": len(matches)},
        )
    job = matches[0]
    raw_format = str(job.get("VideoFormat") or job.get("AudioFormat") or "")
    raw_codec = str(job.get("VideoCodec") or job.get("AudioCodec") or "")
    verified = (
        os.path.realpath(str(job.get("TargetDir") or "")) == os.path.realpath(target_dir)
        and str(job.get("OutputFilename") or job.get("OutputFileName") or "") == output_filename
        and job.get("IsExportVideo") is False
        and job.get("IsExportAudio") is True
        and _normalize_render_preset_name(raw_format) in {"wave", "wav"}
        and _normalize_render_preset_name(raw_codec) in {"linearpcm", "lpcm", "pcm"}
    )
    if not verified:
        raise APICallFailed(
            "Preset-backed audio job did not prove the requested Wave/Linear PCM route.",
            details={
                "job_id": str(job_id),
                "output_filename": str(job.get("OutputFilename") or job.get("OutputFileName") or ""),
                "format": raw_format,
                "codec": raw_codec,
                "export_video": job.get("IsExportVideo"),
                "export_audio": job.get("IsExportAudio"),
            },
        )


def _require_single_render_mode(conn) -> None:
    """Select one-file render mode and prove it before any audio dispatch."""
    project = getattr(conn, "project", None)
    setter = _get_callable(project, "SetCurrentRenderMode")
    getter = _get_callable(project, "GetCurrentRenderMode")
    if setter is None or getter is None:
        raise APICallFailed(
            "Single-clip render mode is required for one exact audio output.",
            details={"requested_mode": 1, "actual_mode": None},
        )
    try:
        applied = setter(1)
    except Exception as exc:
        raise APICallFailed(
            "Single-clip render mode setter failed before audio dispatch.",
            details={"requested_mode": 1, "error": str(exc)},
        ) from exc
    try:
        actual = getter()
    except Exception as exc:
        raise APICallFailed(
            "Single-clip render mode readback failed before audio dispatch.",
            details={"requested_mode": 1, "error": str(exc)},
        ) from exc
    if applied is False or actual != 1:
        raise APICallFailed(
            "Failed to apply single-clip render mode before audio dispatch.",
            details={
                "requested_mode": 1,
                "actual_mode": actual,
                "setter_result": applied,
            },
        )


def _set_audio_render_format_and_codec(
    conn,
    *,
    format_name: str,
    codec_name: Optional[str],
) -> tuple[str, str]:
    """Select an audio output route proven available by the live runtime."""
    resolved_format, _ = _resolve_render_format_selector(conn, format_name)
    try:
        available_codecs = get_render_codecs(conn, resolved_format)
    except APICallFailed:
        available_codecs = None

    if (
        resolved_format.casefold() == "wave"
        and available_codecs == {}
        and _normalize_render_preset_name(str(codec_name or ""))
        == _normalize_render_preset_name("Linear PCM")
    ):
        preset_exists, _ = _render_preset_name_exists(conn, _AUDIO_ONLY_PRESET)
        if preset_exists:
            load_render_preset(conn, _AUDIO_ONLY_PRESET)
            current_getter = _get_callable(
                getattr(conn, "project", None), "GetCurrentRenderFormatAndCodec"
            )
            if current_getter is not None:
                current = None
                for _attempt in range(10):
                    current = current_getter()
                    if isinstance(current, dict):
                        current_format = current.get("format")
                        current_codec = current.get("codec")
                        normalized_format = _normalize_render_preset_name(
                            str(current_format or "")
                        )
                        normalized_codec = _normalize_render_preset_name(
                            str(current_codec or "")
                        )
                        if normalized_format in {"wave", "wav"} and normalized_codec in {
                            "linearpcm",
                            "lpcm",
                            "pcm",
                        }:
                            return current_format, current_codec
                        if normalized_format == "unknown" and normalized_codec == "":
                            # Some native versions hide the active built-in audio
                            # preset behind an opaque current-format response. The
                            # caller must still bind and verify the queued Wave/PCM
                            # job before starting it.
                            return _AUDIO_ONLY_PRESET, ""
                    time.sleep(0.1)
                raise APICallFailed(
                    "Audio Only preset did not read back the requested Wave/Linear PCM route.",
                    details={"current_format_codec": current},
                )
            return _AUDIO_ONLY_PRESET, ""

    return _set_render_format_and_codec(
        conn,
        format_name=format_name,
        codec_name=codec_name,
    )


def _ensure_audio_capable_render_format(conn) -> Dict[str, Any]:
    """Re-base the current render format onto an audio-capable baseline."""
    project = getattr(conn, "project", None)
    before: Any = None
    getter = _get_callable(project, "GetCurrentRenderFormatAndCodec")
    if getter is not None:
        try:
            before = getter()
        except Exception:
            before = None

    setter = _get_callable(project, "SetCurrentRenderFormatAndCodec")
    if setter is None:
        return {"normalized": False, "reason": "setter_unavailable", "before": before}

    for format_name, codec_name in _AUDIO_CAPABLE_FORMAT_CANDIDATES:
        try:
            result = setter(format_name, codec_name)
        except Exception:
            continue
        if result is not False:
            return {
                "normalized": True,
                "format": format_name,
                "codec": codec_name,
                "before": before,
            }
    return {"normalized": False, "reason": "no_candidate_accepted", "before": before}


def render_audio_with_preset(
    conn,
    output_path: str,
    *,
    preset_name: str,
    preset_path: str | None = None,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> str:
    target_dir = _ensure_render_output_dir(output_path)
    base_name = os.path.splitext(os.path.basename(output_path))[0]
    snapshot = None
    job_id: str | None = None
    render_dispatch_attempted = False
    render_completed = False
    render_context_mutated = False
    restore_context = True
    imported_preset_name: str | None = None
    job_ids_before: set[str] = set()

    try:
        project = getattr(conn, "project", None)
        rendering_getter = _get_callable(project, "IsRenderingInProgress")
        list_jobs = _get_callable(project, "GetRenderJobList")
        if rendering_getter is None:
            raise APICallFailed(
                "IsRenderingInProgress is required for non-destructive preset audio rendering.",
                details={"required_api": "Project.IsRenderingInProgress"},
            )
        try:
            rendering_state = rendering_getter()
        except Exception as exc:
            raise APICallFailed(
                "Cannot prove that the render queue is idle.",
                details={"api": "Project.IsRenderingInProgress", "error": str(exc)},
            ) from exc
        if not isinstance(rendering_state, bool):
            raise APICallFailed(
                "Cannot prove that the render queue is idle.",
                details={
                    "api": "Project.IsRenderingInProgress",
                    "reason": "non_boolean_state",
                    "returned_type": type(rendering_state).__name__,
                },
            )
        if rendering_state:
            raise APICallFailed(
                "Cannot render preset audio while another render is in progress.",
                details={
                    "active_render": True,
                    "existing_render_jobs": _get_render_jobs_safely(conn),
                },
            )
        if list_jobs is None:
            raise APICallFailed(
                "GetRenderJobList is required for preset audio job ownership.",
                details={"required_api": "Project.GetRenderJobList"},
            )
        try:
            jobs_before = list(list_jobs() or [])
        except Exception as exc:
            raise APICallFailed(
                "Cannot snapshot the render queue before preset audio rendering.",
                details={"api": "Project.GetRenderJobList", "error": str(exc)},
            ) from exc
        job_ids_before = _render_job_id_set(jobs_before)
        if _get_callable(project, "DeleteRenderJob") is None:
            raise APICallFailed(
                "DeleteRenderJob is required for non-destructive preset audio rendering.",
                details={"required_api": "Project.DeleteRenderJob"},
            )

        snapshot = _snapshot_render_context(conn)
        with _with_required_page(conn, "deliver"):
            render_context_mutated = True
            if preset_path:
                preset_import = import_render_preset(conn, preset_path)
                if preset_import.get("imported") is True:
                    imported_preset_name = str(preset_import["preset_name"])
            _ensure_audio_capable_render_format(conn)
            load_render_preset(conn, preset_name)

            _require_single_render_mode(conn)

            settings = {
                "SelectAllFrames": True,
                "TargetDir": target_dir,
                "CustomName": base_name,
                "ExportVideo": False,
                "ExportAudio": True,
            }

            set_settings = _get_callable(getattr(conn, "project", None), "SetRenderSettings")
            if set_settings is None:
                raise APICallFailed("SetRenderSettings not available.", details={"settings": settings})
            set_result = set_settings(settings)
            if set_result is False:
                raise APICallFailed(
                    "Failed to apply preset-based audio render settings.",
                    details={"settings": settings, "preset_name": preset_name},
                )

            candidate_job_id = str(_add_render_job_with_retry(
                conn,
                error_message="Failed to add preset-based audio render job.",
                details={"settings": settings, "preset_name": preset_name},
            ))
            jobs_after = _get_render_jobs_safely(conn)
            if (
                candidate_job_id in job_ids_before
                or candidate_job_id not in _render_job_id_set(jobs_after)
            ):
                raise APICallFailed(
                    "Cannot prove ownership of the preset audio render job.",
                    details={
                        "candidate_job_id": candidate_job_id,
                        "job_ids_before": sorted(job_ids_before),
                        "job_ids_after": sorted(_render_job_id_set(jobs_after)),
                    },
                )
            job_id = candidate_job_id

            render_dispatch_attempted = True
            try:
                _start_specific_render_job(
                    conn,
                    job_id,
                    error_message="Failed to start preset-based audio render job.",
                    allow_start_all_fallback=False,
                )
            except APICallFailed:
                raise
            except Exception as exc:
                raise APICallFailed(
                    "Failed to start preset-based audio render job.",
                    details={"job_id": job_id, "error": str(exc)},
                ) from exc

            wait_for_render(conn, jobs=job_id)
            render_completed = True

            if progress_callback:
                try:
                    progress_callback(100)
                except Exception:
                    pass

        return _resolve_render_output_path(
            conn,
            target_dir=target_dir,
            base_name=base_name,
            preferred_output_path=output_path,
            error_message="Preset-based audio render completed but output file was not found.",
            job_id=job_id,
        )
    finally:
        cleanup_errors: list[Dict[str, Any]] = []
        if render_dispatch_attempted and not render_completed:
            status = _read_render_job_status(conn, str(job_id))
            terminal = status.get("normalized_status") in (
                _RENDER_COMPLETE_STATUSES | _RENDER_FAILED_STATUSES
            )
            if status.get("available") is True and terminal:
                try:
                    _delete_owned_render_job_verified(
                        conn,
                        str(job_id),
                        protected_job_ids=job_ids_before,
                    )
                except Exception as exc:
                    cleanup_errors.append(
                        {
                            "phase": "delete_owned_render_job",
                            "error": str(exc),
                            "details": dict(getattr(exc, "details", {}) or {}),
                        }
                    )
            else:
                restore_context = False
        elif job_id is not None:
            try:
                _delete_owned_render_job_verified(
                    conn,
                    job_id,
                    protected_job_ids=job_ids_before,
                )
            except Exception as exc:
                cleanup_errors.append(
                    {
                        "phase": "delete_owned_render_job",
                        "error": str(exc),
                        "details": dict(getattr(exc, "details", {}) or {}),
                    }
                )
        restore_error: Exception | None = None
        if restore_context:
            try:
                if imported_preset_name is not None:
                    _delete_owned_render_preset(conn, imported_preset_name)
            except Exception as exc:
                cleanup_errors.append(
                    {"phase": "delete_imported_render_preset", "error": str(exc)}
                )
            try:
                if render_context_mutated:
                    _restore_render_context(conn, snapshot)
                elif (
                    isinstance(snapshot, dict)
                    and snapshot.get("custody") == "render_preset_export"
                ):
                    _discard_render_context_preset_snapshot(conn, snapshot)
            except Exception as exc:
                restore_error = exc
        if cleanup_errors:
            raise APICallFailed(
                "Preset audio render cleanup was not verified.",
                details={
                    "job_id": job_id,
                    "cleanup_errors": cleanup_errors,
                    "render_context_restore_error": (
                        None if restore_error is None else str(restore_error)
                    ),
                },
                recoverability="manual",
            ) from (restore_error or None)
        if restore_error is not None:
            raise restore_error


def render_audio_range(
    conn,
    output_path: str,
    *,
    mark_in_frame: int,
    mark_out_frame: int,
    format: str = "Wave",
    codec: str = "Linear PCM",
    bitdepth: int = 16,
    samplerate: int = 48000,
) -> str:
    if int(mark_out_frame) < int(mark_in_frame):
        raise APICallFailed(
            "Audio render range is invalid.",
            details={"mark_in_frame": mark_in_frame, "mark_out_frame": mark_out_frame},
    )

    bitdepth, samplerate = _validate_audio_render_settings(bitdepth, samplerate)
    _validate_audio_render_codec_request(conn, format=format, codec=codec)
    target_dir = _ensure_render_output_dir(output_path)
    base_name = os.path.splitext(os.path.basename(output_path))[0]
    snapshot = None
    job_id: str | None = None
    render_dispatch_attempted = False
    render_completed = False
    render_context_mutated = False
    restore_context = True
    job_ids_before: set[str] = set()

    try:
        project = getattr(conn, "project", None)
        rendering_getter = _get_callable(project, "IsRenderingInProgress")
        list_jobs = _get_callable(project, "GetRenderJobList")
        if rendering_getter is None:
            raise APICallFailed(
                "IsRenderingInProgress is required for non-destructive audio evidence rendering.",
                details={"required_api": "Project.IsRenderingInProgress"},
            )
        try:
            rendering_state = rendering_getter()
        except Exception as exc:
            raise APICallFailed(
                "Cannot prove that the render queue is idle.",
                details={"api": "Project.IsRenderingInProgress", "error": str(exc)},
            ) from exc
        if not isinstance(rendering_state, bool):
            raise APICallFailed(
                "Cannot prove that the render queue is idle.",
                details={
                    "api": "Project.IsRenderingInProgress",
                    "reason": "non_boolean_state",
                    "returned_type": type(rendering_state).__name__,
                },
            )
        active_render = rendering_state
        if active_render:
            raise APICallFailed(
                "Cannot render an audio evidence range while another render is in progress.",
                details={"active_render": True, "existing_render_jobs": _get_render_jobs_safely(conn)},
            )
        if list_jobs is None:
            raise APICallFailed(
                "GetRenderJobList is required for audio evidence job ownership.",
                details={"required_api": "Project.GetRenderJobList"},
            )
        try:
            jobs_before = list(list_jobs() or [])
        except Exception as exc:
            raise APICallFailed(
                "Cannot snapshot the render queue before audio evidence rendering.",
                details={"api": "Project.GetRenderJobList", "error": str(exc)},
            ) from exc
        job_ids_before = _render_job_id_set(jobs_before)
        if _get_callable(project, "DeleteRenderJob") is None:
            raise APICallFailed(
                "DeleteRenderJob is required for non-destructive audio evidence rendering.",
                details={"required_api": "Project.DeleteRenderJob"},
            )

        # Preset-backed capture creates an owned native preset. Defer it until
        # idle queue and cleanup support are proven, so rejected preflight leaks nothing.
        snapshot = _snapshot_render_context(conn)
        with _with_required_page(conn, "deliver"):
            render_context_mutated = True
            resolved_format, resolved_codec = _set_audio_render_format_and_codec(
                conn, format_name=format, codec_name=codec
            )

            _require_single_render_mode(conn)
            settings = {
                "SelectAllFrames": False,
                "MarkIn": int(mark_in_frame),
                "MarkOut": int(mark_out_frame),
                "TargetDir": target_dir,
                "CustomName": base_name,
                "ExportVideo": False,
                "ExportAudio": True,
                "AudioBitDepth": bitdepth,
                "AudioSampleRate": samplerate,
            }

            set_settings = _get_callable(getattr(conn, "project", None), "SetRenderSettings")
            if set_settings is None:
                raise APICallFailed("SetRenderSettings not available.", details={"settings": settings})
            set_result = set_settings(settings)
            if set_result is False:
                raise APICallFailed(
                    "Failed to apply audio range render settings.",
                    details={
                        "settings": settings,
                        "requested_format": format,
                        "requested_codec": codec,
                        "resolved_format": resolved_format,
                        "resolved_codec": resolved_codec,
                    },
                )

            candidate_job_id = str(_add_render_job_with_retry(
                conn,
                error_message="Failed to add audio range render job.",
                details={"settings": settings},
            ))
            jobs_after = _get_render_jobs_safely(conn)
            if (
                candidate_job_id in job_ids_before
                or candidate_job_id not in _render_job_id_set(jobs_after)
            ):
                raise APICallFailed(
                    "Cannot prove ownership of the audio evidence render job.",
                    details={
                        "candidate_job_id": candidate_job_id,
                        "job_ids_before": sorted(job_ids_before),
                        "job_ids_after": sorted(_render_job_id_set(jobs_after)),
                    },
                )
            job_id = candidate_job_id

            if resolved_format == _AUDIO_ONLY_PRESET and resolved_codec == "":
                _verify_opaque_wave_pcm_job(
                    conn,
                    job_id=job_id,
                    target_dir=target_dir,
                    output_filename=os.path.basename(output_path),
                )

            # The native call may start rendering and then raise or return an
            # ambiguous failure.  From this point onward cleanup requires exact
            # terminal status proof even when the wrapper does not return.
            render_dispatch_attempted = True
            try:
                _start_specific_render_job(
                    conn,
                    job_id,
                    error_message="Failed to start audio range render job.",
                    allow_start_all_fallback=False,
                )
            except APICallFailed:
                raise
            except Exception as exc:
                raise APICallFailed(
                    "Failed to start audio range render job.",
                    details={"job_id": job_id, "error": str(exc)},
                ) from exc
            wait_for_render(conn, jobs=job_id)
            render_completed = True

        return _resolve_render_output_path(
            conn,
            target_dir=target_dir,
            base_name=base_name,
            preferred_output_path=output_path,
            error_message="Render complete but output file not found at expected path.",
            job_id=job_id,
        )
    finally:
        cleanup_error: Exception | None = None
        if render_dispatch_attempted and not render_completed:
            # DaVinci Resolve only exposes a process-global StopRendering call.
            # Never use it from an evidence helper: an external render could win
            # the race after our failure.  Delete our proven-owned job only after
            # its own status explicitly proves terminal; otherwise leave it for
            # recovery and avoid changing live render settings beneath it.
            status = _read_render_job_status(conn, str(job_id))
            terminal = status.get("normalized_status") in (
                _RENDER_COMPLETE_STATUSES | _RENDER_FAILED_STATUSES
            )
            if status.get("available") is True and terminal:
                try:
                    _delete_owned_render_job_verified(
                        conn,
                        str(job_id),
                        protected_job_ids=job_ids_before,
                    )
                except Exception as exc:
                    cleanup_error = exc
            else:
                restore_context = False
        elif job_id is not None:
            try:
                _delete_owned_render_job_verified(
                    conn,
                    job_id,
                    protected_job_ids=job_ids_before,
                )
            except Exception as exc:
                cleanup_error = exc
        restore_error: Exception | None = None
        if restore_context:
            try:
                if render_context_mutated:
                    _restore_render_context(conn, snapshot)
                elif (
                    isinstance(snapshot, dict)
                    and snapshot.get("custody") == "render_preset_export"
                ):
                    _discard_render_context_preset_snapshot(conn, snapshot)
            except Exception as exc:
                restore_error = exc
        if cleanup_error is not None:
            raise APICallFailed(
                "Audio range render cleanup was not verified.",
                details={
                    "job_id": job_id,
                    "cleanup_error": str(cleanup_error),
                    "cleanup_error_details": dict(
                        getattr(cleanup_error, "details", {}) or {}
                    ),
                    "render_context_restore_error": (
                        None if restore_error is None else str(restore_error)
                    ),
                },
                recoverability="manual",
            ) from cleanup_error
        if restore_error is not None:
            raise restore_error


def _transcript_render_diagnostics(
    conn,
    *,
    phase: str,
    preset_name: str,
    preset_path: str,
    runtime_preset: Dict[str, Any] | None = None,
    preset_import: Dict[str, Any] | None = None,
    preset_load: Dict[str, Any] | None = None,
    settings: Dict[str, Any] | None = None,
    format_baseline: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    details: Dict[str, Any] = {
        "phase": phase,
        "preset_name": preset_name,
        "preset_path": preset_path,
    }
    if runtime_preset is not None:
        details["runtime_preset"] = runtime_preset
    if preset_import is not None:
        details["preset_import"] = preset_import
    if preset_load is not None:
        details["preset_load"] = preset_load
    if settings is not None:
        details["settings"] = settings
    if format_baseline is not None:
        details["format_baseline"] = format_baseline

    try:
        details["available_presets"] = _summarize_render_presets(get_render_presets(conn))
    except Exception as exc:
        details["available_presets_error"] = str(exc)

    try:
        details["current_render_settings"] = get_render_settings(conn)
    except Exception as exc:
        details["current_render_settings_error"] = str(exc)

    return details


def _prepare_transcript_runtime_preset(preset_path: str, preset_name: str) -> Dict[str, Any]:
    source_path = _resolve_render_preset_import_path(preset_path)
    runtime_id = str(uuid.uuid4())
    runtime_name = f"{preset_name} {runtime_id[:8]}".strip()

    try:
        tree = ET.parse(source_path)
        root = tree.getroot()
        root.set("DbId", runtime_id)
        for tag, value in (
            ("RecordInfoName", runtime_name),
            ("RecordFormatType", "mp3"),
            ("RecordFormatSubType", "mp3"),
            ("DestSuffix", ""),
        ):
            node = root.find(tag)
            if node is None:
                node = ET.SubElement(root, tag)
            node.text = value or None
        xml_buffer = BytesIO()
        tree.write(xml_buffer, encoding="UTF-8", xml_declaration=True)
        runtime_xml = xml_buffer.getvalue()
    except ImportError as exc:
        if "expat" not in str(exc).lower():
            raise
        xml_text = Path(source_path).read_text(encoding="utf-8")
        root_tag = "SyRecordInfo"
        xml_text = _replace_xml_root_attribute(
            xml_text,
            root_tag=root_tag,
            attr_name="DbId",
            value=runtime_id,
        )
        for tag, value in (
            ("RecordInfoName", runtime_name),
            ("RecordFormatType", "mp3"),
            ("RecordFormatSubType", "mp3"),
            ("DestSuffix", ""),
        ):
            xml_text = _replace_xml_child_text(xml_text, root_tag=root_tag, tag=tag, value=value)
        runtime_xml = xml_text.encode("utf-8")

    temp_dir = Path(tempfile.mkdtemp(prefix="cutagent-transcript-preset-"))
    runtime_bundle_path = temp_dir / f"{runtime_name}.drpx"
    runtime_bundle_path.mkdir()
    runtime_path = runtime_bundle_path / f"{runtime_name}.xml"
    runtime_path.write_bytes(runtime_xml)
    return {
        "name": runtime_name,
        "path": str(runtime_bundle_path),
        "xml_path": str(runtime_path),
        "temp_dir": str(temp_dir),
        "db_id": runtime_id,
        "source_path": str(source_path),
        "requested_name": preset_name,
    }


def _transcript_runtime_preset_was_imported(
    preset_import: Dict[str, Any],
    runtime_preset: Dict[str, Any],
) -> bool:
    if preset_import.get("imported") is not True:
        return False
    if preset_import.get("already_exists") is True:
        return False
    imported_name = str(preset_import.get("preset_name") or "").strip()
    if imported_name and imported_name != str(runtime_preset.get("name")):
        return False
    imported_path = preset_import.get("resolved_path") or preset_import.get("path")
    if imported_path:
        try:
            imported_resolved = Path(imported_path).resolve()
            owned_paths = {
                Path(str(runtime_preset["path"])).resolve(),
                Path(str(runtime_preset.get("xml_path") or runtime_preset["path"])).resolve(),
            }
            if imported_resolved not in owned_paths:
                return False
        except Exception:
            return False
    return True


def _validate_transcript_mp3_output(actual_output_path: str, preferred_output_path: str) -> str:
    actual = Path(actual_output_path).expanduser()
    preferred = Path(preferred_output_path).expanduser()
    if preferred.suffix.casefold() != ".mp3":
        raise ValidationError(
            "Transcript audio output path must end with .mp3.",
            details={"output_path": str(preferred)},
        )
    if actual.suffix.casefold() == ".mp3":
        return str(actual)

    raise APICallFailed(
        "Transcript render preset produced a non-MP3 output.",
        details={
            "actual_output_path": str(actual),
            "preferred_output_path": str(preferred),
            "actual_suffix": actual.suffix,
            "expected_suffix": ".mp3",
            "hint": "Fix the DaVinci Resolve transcript render preset XML/settings so DaVinci Resolve renders MP3 directly.",
        },
    )


def _get_render_jobs_safely(conn) -> list[Any]:
    getter = _get_callable(getattr(conn, "project", None), "GetRenderJobList")
    if getter is None:
        return []
    try:
        jobs = getter()
    except Exception:
        return []
    return list(jobs or []) if isinstance(jobs, list) else []


def _render_job_id_set(jobs: list[Any]) -> set[str]:
    job_ids: set[str] = set()
    for job in jobs:
        value = job.get("JobId") if isinstance(job, dict) else job
        if value is not None and str(value).strip():
            job_ids.add(str(value))
    return job_ids


def _delete_render_job_quietly(conn, job_id: str | None) -> bool:
    if not job_id:
        return False
    delete_job = _get_callable(getattr(conn, "project", None), "DeleteRenderJob")
    if delete_job is None:
        return False
    try:
        return delete_job(str(job_id)) is not False
    except Exception:
        return False


def _delete_owned_render_job_verified(
    conn,
    job_id: str,
    *,
    protected_job_ids: set[str],
) -> None:
    """Delete one proven-owned job and verify the queue retained every prior job."""
    delete_job = _get_callable(getattr(conn, "project", None), "DeleteRenderJob")
    list_jobs = _get_callable(getattr(conn, "project", None), "GetRenderJobList")
    if delete_job is None or list_jobs is None:
        raise APICallFailed(
            "Owned audio render job cleanup cannot be verified.",
            details={
                "job_id": str(job_id),
                "missing_apis": [
                    name
                    for name, method in (
                        ("Project.DeleteRenderJob", delete_job),
                        ("Project.GetRenderJobList", list_jobs),
                    )
                    if method is None
                ],
            },
        )

    delete_result: Any = None
    delete_error: str | None = None
    try:
        delete_result = delete_job(str(job_id))
    except Exception as exc:
        delete_error = str(exc)

    try:
        jobs_after = list_jobs()
    except Exception as exc:
        raise APICallFailed(
            "Owned audio render job cleanup readback failed.",
            details={
                "job_id": str(job_id),
                "delete_result": delete_result,
                "delete_error": delete_error,
                "readback_error": str(exc),
            },
        ) from exc
    if not isinstance(jobs_after, list):
        raise APICallFailed(
            "Owned audio render job cleanup readback was ambiguous.",
            details={
                "job_id": str(job_id),
                "delete_result": delete_result,
                "delete_error": delete_error,
                "returned_type": type(jobs_after).__name__,
            },
        )

    observed_job_ids = _render_job_id_set(jobs_after)
    missing_protected = sorted(protected_job_ids - observed_job_ids)
    if (
        delete_error is not None
        or delete_result is False
        or str(job_id) in observed_job_ids
        or missing_protected
    ):
        raise APICallFailed(
            "Owned audio render job cleanup was not verified.",
            details={
                "job_id": str(job_id),
                "delete_result": delete_result,
                "delete_error": delete_error,
                "owned_job_remained": str(job_id) in observed_job_ids,
                "missing_protected_job_ids": missing_protected,
                "observed_job_ids": sorted(observed_job_ids),
            },
        )


def _prepare_transcript_render_queue(conn) -> Dict[str, Any]:
    jobs_before = _get_render_jobs_safely(conn)
    if _is_rendering_in_progress(conn):
        raise APICallFailed(
            "Cannot render transcript audio while another render is in progress.",
            details={
                "phase": "prepare_render_queue",
                "active_render": True,
                "existing_render_jobs": jobs_before,
            },
        )
    try:
        conn.refresh()
    except Exception:
        pass
    if _is_rendering_in_progress(conn):
        raise APICallFailed(
            "Cannot render transcript audio while another render is in progress.",
            details={
                "phase": "prepare_render_queue",
                "active_render": True,
                "existing_render_jobs": _get_render_jobs_safely(conn),
            },
        )
    return {
        "existing_jobs": jobs_before,
        "existing_job_ids": sorted(_render_job_id_set(jobs_before)),
    }


def render_transcript_audio(
    conn,
    *,
    output_path: str,
    preset_path: str,
    preset_name: str,
) -> Dict[str, Any]:
    if Path(output_path).expanduser().suffix.casefold() != ".mp3":
        raise ValidationError(
            "Transcript audio output path must end with .mp3.",
            details={"output_path": output_path},
        )
    target_dir = os.path.dirname(os.path.abspath(output_path))
    base_name = os.path.splitext(os.path.basename(output_path))[0]
    preset_import = {"imported": False, "path": preset_path, "resolved_path": preset_path}
    runtime_preset: Dict[str, Any] | None = None
    runtime_preset_imported = False
    queue_state: Dict[str, Any] = {"existing_jobs": [], "existing_job_ids": []}
    snapshot = _snapshot_render_context(conn)
    job_id: str | None = None
    render_started = False
    render_completed = False

    try:
        runtime_preset = _prepare_transcript_runtime_preset(preset_path, preset_name)
        queue_state = _prepare_transcript_render_queue(conn)
        with _with_required_page(conn, "deliver"):
            preset_import = import_render_preset(conn, runtime_preset["path"])
            runtime_preset_imported = _transcript_runtime_preset_was_imported(preset_import, runtime_preset)
            format_baseline = {
                "normalized": False,
                "reason": "skipped_for_transcript_mp3_preset",
            }
            try:
                preset_load = load_render_preset(conn, runtime_preset["name"])
            except APICallFailed as exc:
                details = dict(getattr(exc, "details", {}) or {})
                details.update(
                    _transcript_render_diagnostics(
                        conn,
                        phase="load_preset",
                        preset_name=preset_name,
                        preset_path=preset_path,
                        runtime_preset=runtime_preset,
                        preset_import=preset_import,
                        settings=None,
                        format_baseline=format_baseline,
                    )
                )
                raise APICallFailed(str(exc), details=details) from exc

            set_render_mode = _get_callable(getattr(conn, "project", None), "SetCurrentRenderMode")
            if set_render_mode is not None:
                try:
                    set_render_mode(1)
                except Exception:
                    pass

            settings = {
                "SelectAllFrames": True,
                "TargetDir": target_dir,
                "CustomName": base_name,
                "ExportVideo": False,
                "ExportAudio": True,
            }
            set_settings = _get_callable(getattr(conn, "project", None), "SetRenderSettings")
            if set_settings is None:
                raise APICallFailed(
                    "SetRenderSettings not available.",
                    details=_transcript_render_diagnostics(
                        conn,
                        phase="set_render_settings",
                        preset_name=preset_name,
                        preset_path=preset_path,
                        runtime_preset=runtime_preset,
                        preset_import=preset_import,
                        preset_load=preset_load,
                        settings=settings,
                        format_baseline=format_baseline,
                    ),
                )
            set_result = set_settings(settings)
            if set_result is False:
                raise APICallFailed(
                    "Failed to apply transcript render settings.",
                    details=_transcript_render_diagnostics(
                        conn,
                        phase="set_render_settings",
                        preset_name=preset_name,
                        preset_path=preset_path,
                        runtime_preset=runtime_preset,
                        preset_import=preset_import,
                        preset_load=preset_load,
                        settings=settings,
                        format_baseline=format_baseline,
                    ),
                )

            job_id = str(_add_render_job_with_retry(
                conn,
                error_message="Failed to add transcript render job after loading the CutAgent transcript preset.",
                details=_transcript_render_diagnostics(
                    conn,
                    phase="add_render_job",
                    preset_name=preset_name,
                    preset_path=preset_path,
                    runtime_preset=runtime_preset,
                    preset_import=preset_import,
                    preset_load=preset_load,
                    settings=settings,
                    format_baseline=format_baseline,
                ),
            ))

            start_render = _get_callable(getattr(conn, "project", None), "StartRendering")
            if start_render is None:
                raise APICallFailed("StartRendering not available.")
            _start_specific_render_job(
                conn,
                job_id,
                error_message="Failed to start transcript render job.",
                allow_start_all_fallback=not bool(queue_state.get("existing_job_ids")),
            )
            render_started = True
            wait_for_render(conn, jobs=job_id)
            render_completed = True

            actual_output_path = _resolve_render_output_path(
                conn,
                target_dir=target_dir,
                base_name=base_name,
                preferred_output_path=output_path,
                error_message="Transcript render completed but the output file was not found.",
                job_id=job_id,
            )
            final_output_path = _validate_transcript_mp3_output(actual_output_path, output_path)

            return {
                "output_path": final_output_path,
                "job_id": job_id,
                "preset_name": preset_name,
                "preset_path": preset_path,
                "runtime_preset_name": runtime_preset["name"],
                "runtime_preset_db_id": runtime_preset["db_id"],
                "preset_import": preset_import,
                "preset_load": preset_load,
                "format_baseline": format_baseline,
                "render_queue": {
                    "existing_job_ids": queue_state.get("existing_job_ids", []),
                    "deleted_job_id": job_id,
                },
            }
    finally:
        if render_started and not render_completed:
            _abort_render_job(conn, job_id=job_id)
        elif job_id:
            _delete_render_job_quietly(conn, job_id)
        _restore_render_context(conn, snapshot)
        if runtime_preset is not None and runtime_preset_imported:
            try:
                delete_render_preset(conn, runtime_preset["name"])
            except Exception:
                pass
        if runtime_preset is not None:
            try:
                temp_dir = Path(str(runtime_preset.get("temp_dir") or ""))
                if temp_dir.name.startswith("cutagent-transcript-preset-"):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


def import_burnin_preset(conn, path: str) -> Dict[str, Any]:
    """Import a burn-in preset from file."""
    before_names = {
        str(item.get("name")) for item in get_burnin_presets()
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    importer = _get_callable(getattr(conn, "resolve", None), "ImportBurnInPreset")
    if importer is None:
        raise APICallFailed("ImportBurnInPreset not available.")
    result = importer(path)
    if result is False:
        raise APICallFailed(
            "Burn-in preset import failed.",
            details={
                "path": path,
                "hint": "Verify that the file was exported by DaVinci Resolve as a data burn-in preset.",
            },
        )
    after_presets = get_burnin_presets()
    after_names = [
        str(item.get("name")) for item in after_presets
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    added_names = [name for name in after_names if name not in before_names]
    if len(added_names) != 1:
        raise APICallFailed(
            "Burn-in preset import succeeded but its exact catalog identity could not be verified.",
            details={"path": path, "available_presets": _summarize_burnin_presets(after_presets)},
        )
    return {
        "imported": True, "name": added_names[0], "path": path,
        "available_presets": _summarize_burnin_presets(after_presets),
    }


def export_burnin_preset(conn, name: str, path: str) -> Dict[str, Any]:
    """Export a burn-in preset to file."""
    exporter = _get_callable(getattr(conn, "resolve", None), "ExportBurnInPreset")
    if exporter is None:
        raise APICallFailed("ExportBurnInPreset not available.")
    resolved_name, presets, _unlisted_exact = _resolve_burnin_preset_selector(name)
    output_path = Path(path).expanduser()
    owner_uid = os.getuid() if callable(getattr(os, "getuid", None)) else None
    reserved_stat = None
    native_path = output_path
    if output_path.exists() or output_path.is_symlink():
        reserved_stat = output_path.lstat()
        if (
            output_path.is_symlink()
            or not output_path.is_file()
            or (owner_uid is not None and reserved_stat.st_uid != owner_uid)
            or reserved_stat.st_nlink != 1
            or reserved_stat.st_size != 0
            or reserved_stat.st_mode & 0o022
        ):
            raise ValidationError(
                "Burn-in preset export target already exists and is not an empty owned reservation.",
                details={"path": path},
            )
        native_path = output_path.with_name(
            f".{output_path.name}.cutagent-native-{uuid.uuid4()}"
        )
    native_cleanup = None
    try:
        result = exporter(resolved_name, str(native_path))
        if result is not False and reserved_stat is not None:
            if native_path.exists() or native_path.is_symlink():
                native_cleanup = (
                    native_path.lstat(),
                    native_path.is_dir() and not native_path.is_symlink(),
                )
                if owner_uid is not None and native_cleanup[0].st_uid != owner_uid:
                    raise APICallFailed(
                        "Burn-in preset native export is not owned by the current account.",
                        details={"path": path},
                    )
            if native_path.is_symlink():
                raise APICallFailed(
                    "Burn-in preset export did not produce one regular native payload.",
                    details={"path": path},
                )
            if native_path.is_file():
                payload_path = native_path
            elif native_path.is_dir():
                entries = list(native_path.iterdir())
                if (
                    len(entries) != 1
                    or entries[0].is_symlink()
                    or not entries[0].is_file()
                ):
                    raise APICallFailed(
                        "Burn-in preset export did not produce one bounded native payload.",
                        details={"path": path, "entry_count": len(entries)},
                    )
                payload_path = entries[0]
            else:
                raise APICallFailed(
                    "Burn-in preset export did not produce one regular native payload.",
                    details={"path": path},
                )
            native_stat = payload_path.lstat()
            if (
                (owner_uid is not None and native_stat.st_uid != owner_uid)
                or native_stat.st_nlink != 1
                or native_stat.st_size < 1
                or native_stat.st_size > 16 * 1024 * 1024
            ):
                raise APICallFailed(
                    "Burn-in preset export produced invalid or unbounded native bytes.",
                    details={"path": path, "size_bytes": native_stat.st_size},
                )
            current = output_path.lstat()
            if (
                current.st_dev != reserved_stat.st_dev
                or current.st_ino != reserved_stat.st_ino
                or (owner_uid is not None and current.st_uid != owner_uid)
                or current.st_nlink != 1
                or current.st_size != 0
                or current.st_mode & 0o022
            ):
                raise APICallFailed(
                    "Burn-in preset export reservation changed before byte adoption.",
                    details={"path": path},
                )
            source_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                source_fd = os.open(payload_path, source_flags)
            except OSError as exc:
                raise APICallFailed(
                    "Burn-in preset native payload could not be opened safely.",
                    details={"path": path},
                ) from exc
            with os.fdopen(source_fd, "rb") as source:
                opened_source = os.fstat(source.fileno())
                if (
                    opened_source.st_dev != native_stat.st_dev
                    or opened_source.st_ino != native_stat.st_ino
                    or (owner_uid is not None and opened_source.st_uid != owner_uid)
                    or opened_source.st_nlink != 1
                    or opened_source.st_size != native_stat.st_size
                ):
                    raise APICallFailed(
                        "Burn-in preset native payload changed while opening it.",
                        details={"path": path},
                    )
                bytes_value = source.read(16 * 1024 * 1024 + 1)
                closed_source = os.fstat(source.fileno())
                if (
                    len(bytes_value) != native_stat.st_size
                    or len(bytes_value) > 16 * 1024 * 1024
                    or closed_source.st_dev != native_stat.st_dev
                    or closed_source.st_ino != native_stat.st_ino
                    or (owner_uid is not None and closed_source.st_uid != owner_uid)
                    or closed_source.st_nlink != 1
                    or closed_source.st_size != native_stat.st_size
                ):
                    raise APICallFailed(
                        "Burn-in preset native payload changed while reading it.",
                        details={"path": path},
                    )
            with output_path.open("r+b") as destination:
                opened = os.fstat(destination.fileno())
                if (
                    opened.st_dev != reserved_stat.st_dev
                    or opened.st_ino != reserved_stat.st_ino
                    or (owner_uid is not None and opened.st_uid != owner_uid)
                    or opened.st_nlink != 1
                    or opened.st_mode & 0o022
                ):
                    raise APICallFailed(
                        "Burn-in preset export reservation changed while opening it.",
                        details={"path": path},
                    )
                try:
                    destination.write(bytes_value)
                    destination.flush()
                    os.fsync(destination.fileno())
                except Exception:
                    destination.seek(0)
                    destination.truncate(0)
                    destination.flush()
                    os.fsync(destination.fileno())
                    raise
            adopted = output_path.lstat()
            if (
                adopted.st_dev != reserved_stat.st_dev
                or adopted.st_ino != reserved_stat.st_ino
                or (owner_uid is not None and adopted.st_uid != owner_uid)
                or adopted.st_nlink != 1
                or adopted.st_size != len(bytes_value)
                or adopted.st_mode & 0o022
            ):
                raise APICallFailed(
                    "Burn-in preset export reservation did not retain exact identity.",
                    details={"path": path},
                )
    finally:
        if native_path != output_path:
            if native_cleanup is None and (native_path.exists() or native_path.is_symlink()):
                native_cleanup = (
                    native_path.lstat(),
                    native_path.is_dir() and not native_path.is_symlink(),
                )
            if native_cleanup is not None:
                container_before, is_directory = native_cleanup
                container_after = native_path.lstat()
                if (
                    container_after.st_dev != container_before.st_dev
                    or container_after.st_ino != container_before.st_ino
                    or (owner_uid is not None and container_after.st_uid != owner_uid)
                ):
                    raise APICallFailed(
                        "Burn-in preset native export identity changed before cleanup.",
                        details={"path": path},
                    )
                if is_directory:
                    if native_path.is_symlink() or not native_path.is_dir():
                        raise APICallFailed(
                            "Burn-in preset native export type changed before cleanup.",
                            details={"path": path},
                        )
                    shutil.rmtree(native_path)
                else:
                    native_path.unlink()
    if result is False:
        raise APICallFailed(
            "Burn-in preset export failed.",
            details={
                "requested_preset": str(name),
                "resolved_preset": resolved_name,
                "path": path,
                "available_presets": _summarize_burnin_presets(presets),
            },
        )
    return {"exported": bool(result), "name": resolved_name, "requested_name": str(name), "path": path}


def _burnin_render_context_canonical(
    snapshot: Dict[str, Any], preset_name: str
) -> bytes:
    """Return the captured context with only its burn-in selector changed."""
    canonical = str(snapshot.get("canonical_xml") or "").encode("utf-8")
    selector_pattern = re.compile(
        rb"(<RecordSlatePreset(?:\s[^>]*)?>).*?(</RecordSlatePreset\s*>)",
        re.DOTALL,
    )
    if len(selector_pattern.findall(canonical)) != 1:
        raise APICallFailed(
            "DaVinci Resolve render context has an unsupported canonical burn-in selector envelope."
        )
    escaped = (
        preset_name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .encode("utf-8")
    )
    return selector_pattern.sub(
        lambda match: match.group(1) + escaped + match.group(2),
        canonical,
        count=1,
    )


def _activate_burnin_render_context(
    conn, preset_name: str, loader: Callable[[str], Any]
) -> Any:
    """Select one data burn-in preset in the current Deliver context."""
    snapshot = _snapshot_render_context_with_preset(conn)
    baseline_catalog = list(snapshot["preset_catalog_before"])
    source_path = Path(str(snapshot["preset_xml_path"]))
    runtime_name = f"CutAgent burn-in context {uuid.uuid4()}"
    verification_name = f"CutAgent burn-in verify {uuid.uuid4()}"
    runtime_bundle = source_path.parent / f"{runtime_name}.drpx"
    runtime_xml = runtime_bundle / f"{runtime_name}.xml"
    imported = False
    activated = False
    try:
        load_result = loader(preset_name)
        if load_result is False:
            return load_result
        try:
            tree = ET.parse(source_path)
            root = tree.getroot()
        except (OSError, ET.ParseError) as exc:
            raise APICallFailed(
                "DaVinci Resolve render context could not be prepared for burn-in activation.",
                details={"preset_name": preset_name, "error": str(exc)},
            ) from exc
        records = [element for element in root.iter() if element.tag == "SyRecordInfo"]
        selectors = [element for element in root.iter() if element.tag == "RecordSlatePreset"]
        if len(records) != 1 or len(selectors) != 1:
            raise APICallFailed(
                "DaVinci Resolve render context has an unsupported burn-in selector envelope.",
                details={
                    "record_count": len(records),
                    "selector_count": len(selectors),
                },
            )
        records[0].set("DbId", str(uuid.uuid4()))
        selectors[0].text = preset_name
        runtime_bundle.mkdir()
        tree.write(runtime_xml, encoding="UTF-8", xml_declaration=True)

        imported_result = import_render_preset(conn, str(runtime_bundle))
        imported = imported_result.get("imported") is True
        if not imported or imported_result.get("preset_name") != runtime_name:
            raise APICallFailed(
                "Temporary burn-in render preset was not imported with its exact identity.",
                details={"expected": runtime_name, "result": imported_result},
            )
        expected_catalog = set(baseline_catalog) | {snapshot["preset_name"], runtime_name}
        observed_catalog = _render_preset_catalog_names(conn)
        if set(observed_catalog) != expected_catalog or len(observed_catalog) != len(expected_catalog):
            raise APICallFailed(
                "Temporary burn-in render preset changed an ambiguous catalog set.",
                details={
                    "expected": sorted(expected_catalog),
                    "observed": observed_catalog,
                },
            )
        expected = _burnin_render_context_canonical(snapshot, preset_name)
        imported_path, imported_canonical, _settings = _export_render_context_preset(
            conn, runtime_name, source_path.parent / "burnin-imported"
        )
        imported_root = ET.parse(imported_path).getroot()
        imported_selectors = [
            element.text or ""
            for element in imported_root.iter()
            if element.tag == "RecordSlatePreset"
        ]
        if imported_selectors != [preset_name]:
            raise APICallFailed(
                "Imported burn-in render preset lost its exact selector.",
                details={"expected": preset_name, "observed": imported_selectors},
            )
        if imported_canonical != expected:
            raise APICallFailed(
                "Temporary burn-in render preset changed unrelated render context settings.",
                details={
                    "preset_name": preset_name,
                    "expected_sha256": hashlib.sha256(expected).hexdigest(),
                    "observed_sha256": hashlib.sha256(imported_canonical).hexdigest(),
                },
            )
        loaded = load_render_preset(conn, runtime_name)
        if loaded.get("loaded") is not True or loaded.get("preset") != runtime_name:
            raise APICallFailed(
                "Temporary burn-in render preset did not load with its exact identity.",
                details={"expected": runtime_name, "result": loaded},
            )

        saver = _get_callable(getattr(conn, "project", None), "SaveAsNewRenderPreset")
        if saver is None or saver(verification_name) is not True:
            raise APICallFailed(
                "DaVinci Resolve did not confirm burn-in activation verification capture."
            )
        _path, observed, _settings = _export_render_context_preset(
            conn, verification_name, source_path.parent / "burnin-verification"
        )
        if observed != expected:
            raise APICallFailed(
                "DaVinci Resolve did not retain the selected burn-in preset in the Deliver context.",
                details={
                    "preset_name": preset_name,
                    "expected_sha256": hashlib.sha256(expected).hexdigest(),
                    "observed_sha256": hashlib.sha256(observed).hexdigest(),
                },
            )
        activated = True
        return load_result
    finally:
        cleanup_failures: list[Dict[str, Any]] = []
        for owned_name in (verification_name, runtime_name):
            try:
                if owned_name in _render_preset_catalog_names(conn):
                    _delete_owned_render_preset(conn, owned_name)
            except Exception as exc:
                cleanup_failures.append({"name": owned_name, "error": str(exc)})
        try:
            if activated:
                _discard_render_context_preset_snapshot(conn, snapshot)
            else:
                _restore_render_context_from_preset(conn, snapshot)
        except Exception as exc:
            cleanup_failures.append({"phase": "render_context", "error": str(exc)})
        if cleanup_failures:
            raise APICallFailed(
                "Burn-in activation temporary custody could not be released safely.",
                details={
                    "recovery_required": not activated,
                    "cleanup_failures": cleanup_failures,
                },
                recoverability="manual",
            )


def load_burnin_preset(conn, name: str) -> Dict[str, Any]:
    """Load a burn-in preset by name."""
    loader = _get_callable(getattr(conn, "resolve", None), "LoadBurnInPreset")
    if loader is None:
        loader = _get_callable(getattr(conn, "project", None), "LoadBurnInPreset")
    if loader is None:
        raise APICallFailed("LoadBurnInPreset not available.")
    resolved_name, presets, unlisted_exact = _resolve_burnin_preset_selector(name, allow_unlisted_exact=True)
    # DaVinci Resolve can report a successful burn-in preset load from another
    # page without applying it to the Deliver render context. Bind the native
    # load to Deliver so the returned success describes the context that will
    # actually be rendered.
    with _with_required_page(conn, "deliver"):
        # Capture custody before LoadBurnInPreset because the native call itself
        # may change the Deliver context even when later activation fails.
        result = _activate_burnin_render_context(conn, resolved_name, loader)
    if result is False:
        if unlisted_exact:
            raise _burnin_preset_not_found_error(str(name), presets, attempted_exact_load=True)
        raise APICallFailed(
            "Failed to load burn-in preset.",
            details={
                "requested_preset": str(name),
                "resolved_preset": resolved_name,
                "available_presets": _summarize_burnin_presets(presets),
            },
        )
    return {
        "loaded": bool(result),
        "name": resolved_name,
        "requested_name": str(name),
        "unlisted_exact": unlisted_exact,
        "available_presets": _summarize_burnin_presets(get_burnin_presets()),
    }


def delete_render_preset(conn, name: str) -> Dict[str, Any]:
    """Delete a render preset by name when DaVinci Resolve exposes it."""
    deleter = _get_callable(getattr(conn, "resolve", None), "DeleteRenderPreset")
    if deleter is None:
        deleter = _get_callable(getattr(conn, "project", None), "DeleteRenderPreset")
    if deleter is None:
        raise APICallFailed("DeleteRenderPreset not available.")
    result = deleter(name)
    if result is False:
        raise APICallFailed("Failed to delete render preset.", details={"name": name})
    return {"name": name, "deleted": bool(result)}
