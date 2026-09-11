from __future__ import annotations

from contextlib import nullcontext


def _validate_render_add_preconditions(
    conn, job_settings: Dict[str, Any]
) -> Dict[str, Any]:
    render_settings, output_precondition_verified = (
        _render_settings_for_add_precondition(conn)
    )
    target_dir = _first_render_setting(render_settings, _RENDER_TARGET_KEYS)
    custom_name = _first_render_setting(render_settings, _RENDER_NAME_KEYS)
    missing: list[str] = []
    if target_dir is None:
        missing.append("TargetDir")
    if custom_name is None:
        missing.append("CustomName")
    if output_precondition_verified and missing:
        raise ValidationError(
            "Render output target and filename must be configured before adding a render job.",
            details={
                "missing_settings": missing,
                "render_settings": render_settings,
                "job_settings": job_settings,
                "hint": "Run render settings-set --target DIR --name NAME before render add.",
            },
        )
    return {
        "render_settings": render_settings,
        "target_dir": None if target_dir is None else str(target_dir),
        "custom_name": None if custom_name is None else str(custom_name),
        "output_precondition_verified": output_precondition_verified and not missing,
        "missing_settings": missing,
    }


def preview_add_render_job(
    conn,
    mark_in: Optional[str] = None,
    mark_out: Optional[str] = None,
    range_domain: str = "record",
) -> Dict[str, Any]:
    settings = _render_job_settings(conn, mark_in, mark_out, range_domain=range_domain)
    preconditions = _validate_render_add_preconditions(conn, settings)
    queue_size = 0
    try:
        list_jobs = _get_callable(getattr(conn, "project", None), "GetRenderJobList")
        queue = list_jobs() if list_jobs is not None else []
        queue_size = len(queue)
    except Exception:
        pass
    return {
        "settings": settings,
        "range_domain": str(range_domain or "record").strip().lower().replace("_", "-"),
        "queue_size_before": queue_size,
        **preconditions,
    }


def set_render_settings(
    conn,
    target: Optional[str] = None,
    format: Optional[str] = None,
    codec: Optional[str] = None,
    name: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: Optional[float] = None,
    video: Optional[bool] = None,
    audio: Optional[bool] = None,
    audio_codec: Optional[str] = None,
    audio_bit_depth: Optional[int] = None,
    audio_sample_rate: Optional[int] = None,
    full_timeline: bool = False,
) -> None:
    settings = {}
    if full_timeline:
        settings["SelectAllFrames"] = True
    if target:
        settings["TargetDir"] = target
    if name:
        settings["CustomName"] = name
    if video is not None:
        settings["ExportVideo"] = video
    if audio is not None:
        settings["ExportAudio"] = audio
    if width is not None:
        if width <= 0:
            raise ValidationError(
                "Render width must be positive.", details={"width": width}
            )
        settings["FormatWidth"] = width
    if height is not None:
        if height <= 0:
            raise ValidationError(
                "Render height must be positive.", details={"height": height}
            )
        settings["FormatHeight"] = height
    if fps is not None:
        if fps <= 0:
            raise ValidationError(
                "Render frame rate must be positive.", details={"fps": fps}
            )
        settings["FrameRate"] = fps
    if audio_codec:
        settings["AudioCodec"] = audio_codec
    if audio_bit_depth is not None:
        if audio_bit_depth <= 0:
            raise ValidationError(
                "Audio bit depth must be positive.",
                details={"audio_bit_depth": audio_bit_depth},
            )
        settings["AudioBitDepth"] = int(audio_bit_depth)
    if audio_sample_rate is not None:
        if audio_sample_rate <= 0:
            raise ValidationError(
                "Audio sample rate must be positive.",
                details={"audio_sample_rate": audio_sample_rate},
            )
        settings["AudioSampleRate"] = int(audio_sample_rate)

    if codec and not format:
        raise ValidationError(
            "Render codec can only be set together with a render format.",
            details={"codec": codec},
        )

    if format:
        if (
            video is False
            and audio is True
            and _normalize_render_preset_name(format)
            == _normalize_render_preset_name("Wave")
            and _normalize_render_preset_name(str(codec or ""))
            == _normalize_render_preset_name("Linear PCM")
        ):
            with _with_required_page(conn, "deliver"):
                _set_audio_render_format_and_codec(
                    conn, format_name=format, codec_name=codec
                )
        else:
            _set_render_format_and_codec(conn, format_name=format, codec_name=codec)

    if settings:
        set_settings = _get_callable(
            getattr(conn, "project", None), "SetRenderSettings"
        )
        if set_settings is None:
            raise APICallFailed("SetRenderSettings not available.")
        result = set_settings(settings)
        if result is False:
            raise APICallFailed(
                "Failed to apply render settings.", details={"settings": settings}
            )


def set_render_settings_dict(conn, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Set arbitrary render settings keys through Project.SetRenderSettings."""
    if not isinstance(settings, dict):
        raise ValidationError(
            "Render settings payload must be a JSON object.",
            details={"settings": settings},
        )
    setter = _get_callable(getattr(conn, "project", None), "SetRenderSettings")
    if setter is None:
        raise APICallFailed("SetRenderSettings not available.")
    result = setter(settings)
    if result is False:
        raise APICallFailed("SetRenderSettings failed.", details={"settings": settings})
    return {"settings": settings, "updated": bool(result)}


_ALPHA_DEFAULT_FORMAT = "QuickTime"
_ALPHA_DEFAULT_CODEC = "Apple ProRes 4444"
_ALPHA_FORMATS_WITH_SETTINGS = {"mov", "quicktime", "png", "exr", "dpx", "tif", "tiff"}
_ALPHA_CODEC_TOKENS = ("4444", "argb", "bgra", "rgba", "rgb")


def _render_route_supports_alpha_settings(render_settings: Dict[str, Any]) -> bool:
    fmt = (
        str(render_settings.get("format") or render_settings.get("format_label") or "")
        .strip()
        .lower()
    )
    codec = (
        str(render_settings.get("codec") or render_settings.get("codec_label") or "")
        .strip()
        .lower()
    )
    if not fmt:
        return False
    if fmt in {"mov", "quicktime"}:
        return any(token in codec for token in _ALPHA_CODEC_TOKENS)
    if fmt in _ALPHA_FORMATS_WITH_SETTINGS:
        return True
    return False


def set_render_alpha_settings(
    conn, *, enable: bool = True, mode: str = "premultiplied"
) -> Dict[str, Any]:
    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in {"premultiplied", "straight"}:
        raise ValidationError(
            "Invalid alpha mode. Use premultiplied or straight.", details={"mode": mode}
        )

    requested_settings = {"ExportAlpha": bool(enable), "AlphaMode": normalized_mode}
    # DaVinci Resolve's Project.SetRenderSettings wire token is numeric even
    # though CutAgent exposes a named public enum.
    native_settings = {
        "ExportAlpha": bool(enable),
        "AlphaMode": 0 if normalized_mode == "premultiplied" else 1,
    }
    before = get_render_settings(conn)
    route_supports_alpha = _render_route_supports_alpha_settings(before)

    if not enable and not route_supports_alpha:
        return {
            "settings": requested_settings,
            "updated": False,
            "noop": True,
            "reason": "current_render_route_does_not_support_alpha_settings",
            "current_render_settings": before,
        }

    resolved_format = None
    resolved_codec = None
    format_changed = False
    with _with_required_page(conn, "deliver"):
        if enable and not route_supports_alpha:
            resolved_format, resolved_codec = _set_render_format_and_codec(
                conn,
                format_name=_ALPHA_DEFAULT_FORMAT,
                codec_name=_ALPHA_DEFAULT_CODEC,
            )
            format_changed = True

        setter = _get_callable(getattr(conn, "project", None), "SetRenderSettings")
        if setter is None:
            raise APICallFailed(
                "SetRenderSettings not available.",
                details={"settings": requested_settings},
            )
        result = setter(native_settings)
        if result is False:
            raise APICallFailed(
                "SetRenderSettings failed.",
                details={
                    "settings": native_settings,
                    "current_render_settings": before,
                    "format_changed": format_changed,
                    "resolved_format": resolved_format,
                    "resolved_codec": resolved_codec,
                },
            )

    after = get_render_settings(conn)
    return {
        "settings": requested_settings,
        "updated": bool(result),
        "noop": False,
        "format_changed": format_changed,
        "default_alpha_format": _ALPHA_DEFAULT_FORMAT if format_changed else None,
        "default_alpha_codec": _ALPHA_DEFAULT_CODEC if format_changed else None,
        "resolved_format": resolved_format,
        "resolved_codec": resolved_codec,
        "previous_render_settings": before,
        "current_render_settings": after,
    }


def set_render_setting_key(conn, key: str, value: Any) -> Dict[str, Any]:
    """Set a single render setting key."""
    return set_render_settings_dict(conn, {str(key): value})


def set_archive_render_settings(
    conn,
    *,
    target: Optional[str] = None,
    name: Optional[str] = None,
    format: str = "QuickTime",
    codec: Optional[str] = "Apple ProRes",
    audio_codec: str = "Linear PCM",
    audio_bit_depth: int = 32,
    audio_sample_rate: int = 48000,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: Optional[float] = None,
    separate_audio_tracks: bool = True,
) -> Dict[str, Any]:
    """Configure high-quality archive render settings via public DaVinci Resolve API."""
    set_render_settings(
        conn,
        target=target,
        format=format,
        codec=codec,
        name=name,
        width=width,
        height=height,
        fps=fps,
        video=True,
        audio=True,
        audio_codec=audio_codec,
        audio_bit_depth=audio_bit_depth,
        audio_sample_rate=audio_sample_rate,
    )
    separate_audio_tracks_result = {
        "requested": bool(separate_audio_tracks),
        "configured": False,
        "engine": "not_available",
        "reason": (
            "DaVinci Resolve's public Project.SetRenderSettings API documents video/audio export flags "
            "and audio codec/depth/sample-rate settings, but not the Deliver-page control that maps all "
            "timeline audio tracks to separate embedded output tracks."
        ),
        "safe_next_step": (
            "Use a prepared DaVinci Resolve render preset for per-track embedded audio, then load it with "
            "`cutagent render preset-load` before `render add`."
        ),
    }
    if not separate_audio_tracks:
        separate_audio_tracks_result.update(
            {
                "configured": True,
                "engine": "api_native",
                "reason": "Archive settings are configured for the main rendered audio mix.",
                "safe_next_step": None,
            }
        )
    return {
        "action": "render.archive_settings",
        "configured": True,
        "settings": {
            "TargetDir": target,
            "CustomName": name,
            "Format": format,
            "Codec": codec,
            "ExportVideo": True,
            "ExportAudio": True,
            "AudioCodec": audio_codec,
            "AudioBitDepth": int(audio_bit_depth),
            "AudioSampleRate": int(audio_sample_rate),
            "FormatWidth": width,
            "FormatHeight": height,
            "FrameRate": fps,
        },
        "separate_embedded_audio_tracks": separate_audio_tracks_result,
    }


def _render_preset_catalog_names(conn) -> list[str]:
    presets = get_render_presets(conn)
    names = [_render_preset_name(preset) for preset in presets]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise APICallFailed(
            "DaVinci Resolve render preset catalog is incomplete or ambiguous.",
            details={"available_presets": _summarize_render_presets(presets)},
        )
    return [str(name) for name in names]


def _render_preset_text(root: ET.Element, tag: str) -> str:
    values = [element.text or "" for element in root.iter() if element.tag == tag]
    if len(values) != 1:
        raise APICallFailed(
            "DaVinci Resolve render preset snapshot has an ambiguous settings envelope.",
            details={"field": tag, "value_count": len(values)},
        )
    return values[0]


def _render_preset_bool(root: ET.Element, tag: str) -> bool:
    value = _render_preset_text(root, tag).strip().lower()
    if value not in {"true", "false"}:
        raise APICallFailed(
            "DaVinci Resolve render preset snapshot contains an unsupported boolean value.",
            details={"field": tag, "value": value},
        )
    return value == "true"


def _render_preset_int(root: ET.Element, tag: str) -> int:
    value = _render_preset_text(root, tag).strip()
    try:
        return int(value)
    except ValueError as exc:
        raise APICallFailed(
            "DaVinci Resolve render preset snapshot contains an unsupported integer value.",
            details={"field": tag, "value": value},
        ) from exc


def _render_preset_restore_settings(root: ET.Element) -> Dict[str, Any]:
    record_mode = _render_preset_text(root, "RecordMode").strip()
    if record_mode == "RECORD_MODE_NONE":
        select_all_frames = True
    elif record_mode == "RECORD_MODE_IN_OUT":
        select_all_frames = False
    else:
        raise APICallFailed(
            "DaVinci Resolve render preset snapshot contains an unsupported range mode.",
            details={"record_mode": record_mode},
        )
    render_format = _render_preset_text(root, "RecordFormatType").strip().lower()
    if not render_format:
        raise APICallFailed(
            "DaVinci Resolve render preset snapshot does not identify its render format."
        )
    # Movie containers can also be audio-only. The explicit FieldsBlob flag
    # overrides the container default (native MP4/AAC capture proves this case).
    export_video = render_format not in {"wav", "wave", "aif", "aiff", "mp3"}
    blobs = [element.text or "" for element in root.iter() if element.tag == "FieldsBlob"]
    if len(blobs) > 1:
        raise APICallFailed("Render preset has ambiguous FieldsBlob state.")
    if blobs:
        from .fairlight_ops import _decode_bmd_fields_blob_entries

        try:
            version, entries = _decode_bmd_fields_blob_entries(bytes.fromhex(blobs[0]))
        except (ValueError, ValidationError) as exc:
            raise APICallFailed("Render preset FieldsBlob cannot be decoded completely.") from exc
        flags = [entry for entry in entries if entry["key"] == "RecordVideoEnabled"]
        if version != 1 or len(flags) > 1:
            raise APICallFailed("Render preset has unsupported video-enabled state.")
        if flags:
            flag = flags[0]
            if flag["value_type"] != 1 or flag["value_raw"] not in (b"\x00\x00", b"\x00\x01"):
                raise APICallFailed("Render preset has invalid video-enabled state.")
            export_video = flag["value_raw"] == b"\x00\x01"
    return {
        "TargetDir": _render_preset_text(root, "RecordTargetDir"),
        "CustomName": _render_preset_text(root, "RecordPrefix"),
        "ExportVideo": export_video,
        "ExportAudio": _render_preset_bool(root, "RecordAudioEnabled"),
        "SelectAllFrames": select_all_frames,
        "MarkIn": _render_preset_int(root, "RecordStartFrame"),
        "MarkOut": _render_preset_int(root, "RecordEndFrame"),
    }


def _canonical_render_preset_xml(path: Path) -> tuple[bytes, Dict[str, Any]]:
    try:
        raw = path.read_bytes()
        root = ET.fromstring(raw)
    except (OSError, ET.ParseError) as exc:
        raise APICallFailed(
            "DaVinci Resolve exported an unreadable render preset snapshot.",
            details={"path": str(path), "error": str(exc)},
        ) from exc
    records = [element for element in root.iter() if element.tag == "SyRecordInfo"]
    prefixes = [element for element in root.iter() if element.tag == "RecordPrefix"]
    db_id_pattern = re.compile(rb'(<SyRecordInfo\b[^>]*\bDbId=")[^"]*(")')
    if len(records) != 1 or len(prefixes) != 1 or len(db_id_pattern.findall(raw)) != 1:
        raise APICallFailed(
            "DaVinci Resolve render preset snapshot has an unsupported identity envelope.",
            details={
                "path": str(path),
                "record_count": len(records),
                "record_prefix_count": len(prefixes),
            },
        )
    # Live exports prove this UUID is regenerated for otherwise identical presets.
    canonical = db_id_pattern.sub(rb"\1CUTAGENT_VOLATILE_DB_ID\2", raw, count=1)
    fields_blob_pattern = re.compile(
        rb"(<FieldsBlob>)([0-9A-Fa-f]*)(</FieldsBlob>)"
    )
    fields_blobs = list(fields_blob_pattern.finditer(canonical))
    if len(fields_blobs) > 1:
        raise APICallFailed("Render preset has ambiguous FieldsBlob state.")
    if fields_blobs:
        from .fairlight_ops import (
            _decode_bmd_fields_blob_entries,
            _encode_bmd_fields_blob_entries,
        )

        try:
            version, entries = _decode_bmd_fields_blob_entries(
                bytes.fromhex(fields_blobs[0].group(2).decode("ascii"))
            )
        except (ValueError, ValidationError) as exc:
            raise APICallFailed(
                "Render preset FieldsBlob cannot be decoded completely."
            ) from exc
        resolution_entries = [
            entry for entry in entries if entry["key"] == "UseTimelineResolution"
        ]
        if len(resolution_entries) > 1:
            raise APICallFailed(
                "Render preset has ambiguous timeline-resolution state."
            )
        if resolution_entries:
            resolution_entry = resolution_entries[0]
            if resolution_entry["value_type"] != 1 or resolution_entry[
                "value_raw"
            ] not in (b"\x00\x00", b"\x00\x01"):
                raise APICallFailed(
                    "Render preset has invalid timeline-resolution state."
                )
            # DaVinci Resolve 21.0.0.47 re-exports an omitted/default value as an
            # explicit true value after loading the same preset. Normalize only
            # that native default representation; explicit false remains exact.
            if resolution_entry["value_raw"] == b"\x00\x01":
                entries = [entry for entry in entries if entry is not resolution_entry]
                encoded = _encode_bmd_fields_blob_entries(version, entries).hex().encode(
                    "ascii"
                )
                canonical = fields_blob_pattern.sub(
                    lambda match: match.group(1) + encoded + match.group(3),
                    canonical,
                    count=1,
                )
    return canonical, _render_preset_restore_settings(root)


def _delete_owned_render_preset(conn, name: str) -> None:
    delete_render_preset(conn, name)
    if name in _render_preset_catalog_names(conn):
        raise APICallFailed(
            "Temporary render preset remained after deletion.",
            details={"name": name},
        )


def _export_render_context_preset(
    conn, name: str, directory: Path
) -> tuple[Path, bytes, Dict[str, Any]]:
    bundle = directory / f"{name}.drpx"
    exported = export_render_preset(conn, name, str(bundle))
    if exported.get("exported") is not True:
        raise APICallFailed(
            "DaVinci Resolve did not confirm render preset export.",
            details={"name": name, "export": exported},
        )
    xml_path = _resolve_render_preset_import_path(str(bundle))
    canonical, restore_settings = _canonical_render_preset_xml(xml_path)
    return xml_path, canonical, restore_settings


def _snapshot_render_context_with_preset(conn) -> Dict[str, Any]:
    project = getattr(conn, "project", None)
    saver = _get_callable(project, "SaveAsNewRenderPreset")
    required_apis = {
        "Project.SaveAsNewRenderPreset": saver,
        "Project.LoadRenderPreset": _get_callable(project, "LoadRenderPreset"),
        "Project.SetRenderSettings": _get_callable(project, "SetRenderSettings"),
        "Project.GetCurrentRenderFormatAndCodec": _get_callable(
            project, "GetCurrentRenderFormatAndCodec"
        ),
        "Project.SetCurrentRenderFormatAndCodec": _get_callable(
            project, "SetCurrentRenderFormatAndCodec"
        ),
        "Project.GetCurrentRenderMode": _get_callable(project, "GetCurrentRenderMode"),
        "Project.SetCurrentRenderMode": _get_callable(project, "SetCurrentRenderMode"),
        "Resolve.ExportRenderPreset": _get_callable(
            getattr(conn, "resolve", None), "ExportRenderPreset"
        ),
        "DeleteRenderPreset": _get_callable(
            getattr(conn, "resolve", None), "DeleteRenderPreset"
        )
        or _get_callable(project, "DeleteRenderPreset"),
    }
    missing_apis = [name for name, method in required_apis.items() if method is None]
    if missing_apis:
        raise APICallFailed(
            "DaVinci Resolve render context cannot be captured without GetRenderSettings or render preset custody.",
            details={"recovery_required": False, "missing_apis": missing_apis},
            recoverability="not_applicable",
        )
    before_catalog = _render_preset_catalog_names(conn)
    name = f"CutAgent context {uuid.uuid4()}"
    directory = Path(tempfile.mkdtemp(prefix="cutagent-render-context-"))
    created = False
    try:
        save_result = saver(name)
        after_catalog = _render_preset_catalog_names(conn)
        created = name in after_catalog and name not in before_catalog
        if save_result is not True:
            raise APICallFailed(
                "DaVinci Resolve did not confirm temporary render preset creation."
            )
        if set(after_catalog) - set(before_catalog) != {name} or set(
            before_catalog
        ) - set(after_catalog):
            raise APICallFailed(
                "Temporary render preset creation changed an ambiguous catalog set.",
                details={
                    "before": before_catalog,
                    "after": after_catalog,
                    "owned_name": name,
                },
            )
        format_and_codec = required_apis["Project.GetCurrentRenderFormatAndCodec"]()
        render_mode = required_apis["Project.GetCurrentRenderMode"]()
        if (
            not isinstance(format_and_codec, dict)
            or not isinstance(format_and_codec.get("format"), str)
            or not format_and_codec["format"]
            or not isinstance(format_and_codec.get("codec"), str)
            or not format_and_codec["codec"]
            or render_mode not in {0, 1}
        ):
            raise APICallFailed(
                "DaVinci Resolve render context getter returned an incomplete preset custody snapshot.",
                details={
                    "format_and_codec": format_and_codec,
                    "render_mode": render_mode,
                },
            )
        xml_path, canonical, restore_settings = _export_render_context_preset(
            conn, name, directory
        )
        return {
            "custody": "render_preset_export",
            "preset_name": name,
            "preset_directory": str(directory),
            "preset_xml_path": str(xml_path),
            "canonical_xml_sha256": hashlib.sha256(canonical).hexdigest(),
            "canonical_xml": canonical.decode("utf-8"),
            "restore_settings": restore_settings,
            "format": format_and_codec["format"],
            "codec": format_and_codec["codec"],
            "render_mode": render_mode,
            "preset_catalog_before": before_catalog,
        }
    except Exception as exc:
        cleanup_errors = []
        if created:
            try:
                _delete_owned_render_preset(conn, name)
            except Exception as cleanup_exc:
                cleanup_errors.append(str(cleanup_exc))
        try:
            observed_catalog = _render_preset_catalog_names(conn)
            if observed_catalog != before_catalog:
                cleanup_errors.append(
                    f"render preset catalog changed: expected {before_catalog!r}, observed {observed_catalog!r}"
                )
        except Exception as cleanup_exc:
            cleanup_errors.append(str(cleanup_exc))
        shutil.rmtree(directory, ignore_errors=True)
        if cleanup_errors:
            raise APICallFailed(
                "Render context snapshot failed and temporary preset cleanup was not verified.",
                details={
                    "recovery_required": True,
                    "error": str(exc),
                    "cleanup_errors": cleanup_errors,
                },
                recoverability="manual",
            ) from exc
        raise


def _snapshot_render_context(conn) -> Dict[str, Any]:
    project = getattr(conn, "project", None)
    missing: list[str] = []
    failures: list[Dict[str, Any]] = []
    get_settings = _get_callable(project, "GetRenderSettings")
    get_format = _get_callable(project, "GetCurrentRenderFormatAndCodec")
    get_mode = _get_callable(project, "GetCurrentRenderMode")
    for name, getter in (
        ("Project.GetRenderSettings", get_settings),
        ("Project.GetCurrentRenderFormatAndCodec", get_format),
        ("Project.GetCurrentRenderMode", get_mode),
    ):
        if getter is None:
            missing.append(name)
    settings_unavailable = get_settings is None
    try:
        settings = get_settings() if get_settings is not None else None
    except Exception as exc:
        settings = None
        if isinstance(exc, (TypeError, AttributeError)) or _method_unavailable_error(
            exc
        ):
            settings_unavailable = True
        else:
            failures.append({"api": "Project.GetRenderSettings", "error": str(exc)})
    if settings_unavailable or settings is None:
        if failures:
            raise APICallFailed(
                "DaVinci Resolve render context cannot be captured completely before mutation.",
                details={"recovery_required": False, "read_failures": failures},
                recoverability="not_applicable",
            )
        return _snapshot_render_context_with_preset(conn)
    try:
        format_and_codec = get_format() if get_format is not None else None
    except Exception as exc:
        format_and_codec = None
        failures.append(
            {"api": "Project.GetCurrentRenderFormatAndCodec", "error": str(exc)}
        )
    try:
        render_mode = get_mode() if get_mode is not None else None
    except Exception as exc:
        render_mode = None
        failures.append({"api": "Project.GetCurrentRenderMode", "error": str(exc)})
    render_format = None
    render_codec = None
    if isinstance(format_and_codec, dict):
        render_format = (
            format_and_codec.get("format")
            or format_and_codec.get("Format")
            or format_and_codec.get("format_name")
        )
        render_codec = (
            format_and_codec.get("codec")
            or format_and_codec.get("Codec")
            or format_and_codec.get("codec_name")
        )
    if (
        missing
        or failures
        or not isinstance(settings, dict)
        or not settings
        or not isinstance(render_format, str)
        or not render_format
        or not isinstance(render_codec, str)
        or not render_codec
        or render_mode is None
    ):
        raise APICallFailed(
            "DaVinci Resolve render context cannot be captured completely before mutation.",
            details={
                "recovery_required": False,
                "missing_apis": missing,
                "read_failures": failures,
                "settings_available": isinstance(settings, dict) and bool(settings),
                "format_available": isinstance(render_format, str)
                and bool(render_format),
                "codec_available": isinstance(render_codec, str) and bool(render_codec),
                "render_mode_available": render_mode is not None,
            },
            recoverability="not_applicable",
        )
    return {
        "settings": dict(settings),
        "format": render_format,
        "codec": render_codec,
        "render_mode": render_mode,
    }


def _replay_render_context_from_preset(
    conn, snapshot: Dict[str, Any], *, include_empty_target: bool
) -> None:
    project = getattr(conn, "project", None)
    format_setter = _get_callable(project, "SetCurrentRenderFormatAndCodec")
    format_getter = _get_callable(project, "GetCurrentRenderFormatAndCodec")
    mode_setter = _get_callable(project, "SetCurrentRenderMode")
    mode_getter = _get_callable(project, "GetCurrentRenderMode")
    setter = _get_callable(project, "SetRenderSettings")
    current_format = format_getter() if format_getter is not None else None
    format_already_restored = (
        isinstance(current_format, dict)
        and current_format.get("format") == snapshot["format"]
        and current_format.get("codec") == snapshot["codec"]
    )
    # Loading the retained preset also restores encoder-specific parameters.
    # Re-selecting its already active codec can discard those parameters.
    # The complete exported preset is still compared after replay below.
    if not format_already_restored and (
        format_setter is None
        or format_setter(snapshot["format"], snapshot["codec"]) is not True
    ):
        raise APICallFailed(
            "DaVinci Resolve did not confirm render format and codec restoration."
        )
    try:
        current_mode = mode_getter() if mode_getter is not None else None
    except Exception:
        current_mode = None
    mode_already_restored = (
        current_mode in {0, 1} and current_mode == snapshot["render_mode"]
    )
    # Reapplying the already active mode can reset custom render dimensions.
    if not mode_already_restored and (
        mode_setter is None or mode_setter(snapshot["render_mode"]) is not True
    ):
        raise APICallFailed("DaVinci Resolve did not confirm render mode restoration.")
    restore_settings = snapshot["restore_settings"]
    if not isinstance(restore_settings, dict):
        raise APICallFailed("Stored render settings restoration envelope is invalid.")
    # Reapplying even unchanged ExportAudio/ExportVideo values can discard the
    # preset's encoder parameter map. Read the actual native export after load
    # and restore only settings that the preset did not restore itself.
    observed_snapshot = _snapshot_render_context_with_preset(conn)
    try:
        observed_settings = observed_snapshot["restore_settings"]
    finally:
        _discard_render_context_preset_snapshot(conn, observed_snapshot)
    range_settings = {
        "SelectAllFrames": False,
        "MarkIn": restore_settings.get("MarkIn"),
        "MarkOut": restore_settings.get("MarkOut"),
    }
    range_changed = any(
        observed_settings.get(key) != restore_settings.get(key)
        for key in ("MarkIn", "MarkOut")
    )
    if range_changed and (setter is None or setter(range_settings) is not True):
        raise APICallFailed(
            "DaVinci Resolve did not confirm explicit render range restoration.",
            details={"settings": range_settings},
        )
    final_settings = {
        key: value for key, value in restore_settings.items()
        if key not in {"MarkIn", "MarkOut"} and observed_settings.get(key) != value
    }
    if range_changed:
        final_settings["SelectAllFrames"] = restore_settings["SelectAllFrames"]
    if final_settings.get("TargetDir") == "" and not include_empty_target:
        final_settings.pop("TargetDir")
    if final_settings and (setter is None or setter(final_settings) is not True):
        raise APICallFailed(
            "DaVinci Resolve did not confirm explicit render settings restoration.",
            details={"settings": final_settings},
        )


def _restore_render_context_from_preset(
    conn, snapshot: Dict[str, Any], *, require_deliver_page: bool = True
) -> None:
    required = {
        "preset_name",
        "preset_directory",
        "preset_xml_path",
        "canonical_xml",
        "canonical_xml_sha256",
        "restore_settings",
        "format",
        "codec",
        "render_mode",
        "preset_catalog_before",
    }
    if not required.issubset(snapshot) or not isinstance(
        snapshot.get("preset_catalog_before"), list
    ):
        raise APICallFailed(
            "DaVinci Resolve render preset custody snapshot is incomplete.",
            details={
                "recovery_required": True,
                "reason": "invalid_render_preset_snapshot",
            },
            recoverability="manual",
        )
    name = str(snapshot["preset_name"])
    directory = Path(str(snapshot["preset_directory"]))
    selection_breaker_name = f"CutAgent context selection {uuid.uuid4()}"
    verification_name = f"CutAgent context verify {uuid.uuid4()}"
    owned_names = [name]
    failures: list[Dict[str, Any]] = []
    try:
        expected = str(snapshot["canonical_xml"]).encode("utf-8")
        if hashlib.sha256(expected).hexdigest() != snapshot["canonical_xml_sha256"]:
            raise APICallFailed("Stored render context custody digest is invalid.")
        before_catalog = [str(value) for value in snapshot["preset_catalog_before"]]
        retained_catalog = _render_preset_catalog_names(conn)
        if set(retained_catalog) - set(before_catalog) != {name} or set(
            before_catalog
        ) - set(retained_catalog):
            raise APICallFailed(
                "Retained render context preset custody is missing or ambiguous.",
                details={
                    "before": before_catalog,
                    "observed": retained_catalog,
                    "owned_name": name,
                },
            )
        _path, retained_canonical, _restore_settings = _export_render_context_preset(
            conn,
            name,
            directory / "retained",
        )
        if retained_canonical != expected:
            raise APICallFailed(
                "Retained render context preset no longer matches its captured export.",
                details={
                    "expected_sha256": snapshot["canonical_xml_sha256"],
                    "observed_sha256": hashlib.sha256(retained_canonical).hexdigest(),
                },
            )
        page_context = (
            _with_required_page(conn, "deliver")
            if require_deliver_page
            else nullcontext()
        )
        with page_context:
            # SaveAsNewRenderPreset selects the captured preset. DaVinci Resolve
            # can later change current settings without changing that selection,
            # and loading the already selected preset is then a native no-op.
            # Select a separately owned preset first so loading the retained
            # custody preset must replay its complete encoder/settings payload.
            saver = _get_callable(
                getattr(conn, "project", None), "SaveAsNewRenderPreset"
            )
            if saver is None:
                raise APICallFailed(
                    "SaveAsNewRenderPreset became unavailable during restoration."
                )
            selection_result = saver(selection_breaker_name)
            observed = _render_preset_catalog_names(conn)
            if (
                selection_breaker_name in observed
                and selection_breaker_name not in snapshot["preset_catalog_before"]
            ):
                owned_names.append(selection_breaker_name)
            if selection_result is not True:
                raise APICallFailed(
                    "DaVinci Resolve did not confirm render context selection reset."
                )
            if set(observed) - set(before_catalog) != set(owned_names) or set(
                before_catalog
            ) - set(observed):
                raise APICallFailed(
                    "Render context selection reset changed an ambiguous catalog set.",
                    details={
                        "before": before_catalog,
                        "after": observed,
                        "owned_names": owned_names,
                    },
                )
            load_render_preset(conn, name)
            _replay_render_context_from_preset(
                conn, snapshot, include_empty_target=True
            )
            getattr(conn, "project", None)
            save_result = saver(verification_name)
            observed = _render_preset_catalog_names(conn)
            if (
                verification_name in observed
                and verification_name not in snapshot["preset_catalog_before"]
            ):
                owned_names.append(verification_name)
            if save_result is not True:
                raise APICallFailed(
                    "DaVinci Resolve did not confirm restoration verification preset creation."
                )
            if set(observed) - set(before_catalog) != set(owned_names) or set(
                before_catalog
            ) - set(observed):
                raise APICallFailed(
                    "Render context verification preset changed an ambiguous catalog set.",
                    details={
                        "before": before_catalog,
                        "after": observed,
                        "owned_names": owned_names,
                    },
                )
            _path, canonical, _restore_settings = _export_render_context_preset(
                conn,
                verification_name,
                directory,
            )
            if canonical != expected:
                raise APICallFailed(
                    "DaVinci Resolve render preset load did not restore the exact exported context.",
                    details={
                        "expected_sha256": snapshot["canonical_xml_sha256"],
                        "observed_sha256": hashlib.sha256(canonical).hexdigest(),
                    },
                )
    except Exception as exc:
        failures.append({"phase": "restore_and_verify", "error": str(exc)})
    finally:
        for owned_name in reversed(owned_names):
            try:
                _delete_owned_render_preset(conn, owned_name)
            except Exception as exc:
                failures.append(
                    {
                        "phase": "delete_temporary_preset",
                        "name": owned_name,
                        "error": str(exc),
                    }
                )
        try:
            observed_catalog = _render_preset_catalog_names(conn)
            if observed_catalog != snapshot["preset_catalog_before"]:
                failures.append(
                    {
                        "phase": "verify_preset_catalog",
                        "expected": snapshot["preset_catalog_before"],
                        "observed": observed_catalog,
                    }
                )
        except Exception as exc:
            failures.append({"phase": "verify_preset_catalog", "error": str(exc)})
        shutil.rmtree(directory, ignore_errors=True)
        if directory.exists():
            failures.append({"phase": "delete_temporary_files", "path": str(directory)})
    if not failures:
        observed_snapshot = None
        try:
            observed_snapshot = _snapshot_render_context_with_preset(conn)
            if observed_snapshot["canonical_xml"] != snapshot["canonical_xml"]:
                raise APICallFailed(
                    "Render context changed after restoration cleanup.",
                    details={
                        "expected_sha256": snapshot["canonical_xml_sha256"],
                        "observed_sha256": observed_snapshot[
                            "canonical_xml_sha256"
                        ],
                    },
                )
        except Exception as exc:
            failures.append({"phase": "verify_after_cleanup", "error": str(exc)})
        finally:
            if observed_snapshot is not None:
                try:
                    _discard_render_context_preset_snapshot(conn, observed_snapshot)
                except Exception as exc:
                    failures.append(
                        {"phase": "verify_after_cleanup_release", "error": str(exc)}
                    )
    if failures:
        raise APICallFailed(
            "DaVinci Resolve render context could not be restored and verified.",
            details={"recovery_required": True, "restore_failures": failures},
            recoverability="manual",
        )


def _discard_render_context_preset_snapshot(conn, snapshot: Dict[str, Any]) -> None:
    name = str(snapshot.get("preset_name") or "")
    directory = Path(str(snapshot.get("preset_directory") or ""))
    if (
        not name
        or not directory.is_absolute()
        or not directory.name.startswith("cutagent-render-context-")
    ):
        raise APICallFailed(
            "Temporary render context custody identity is invalid; refusing cleanup.",
            details={"name": name, "directory": str(directory)},
            recoverability="manual",
        )
    failures: list[str] = []
    try:
        catalog = _render_preset_catalog_names(conn)
        if name in catalog:
            _delete_owned_render_preset(conn, name)
        expected = snapshot.get("preset_catalog_before")
        observed = _render_preset_catalog_names(conn)
        if observed != expected:
            failures.append(
                f"preset catalog mismatch: expected {expected!r}, observed {observed!r}"
            )
    except Exception as exc:
        failures.append(str(exc))
    shutil.rmtree(directory, ignore_errors=True)
    if directory.exists():
        failures.append(f"temporary preset directory remained: {directory}")
    if failures:
        raise APICallFailed(
            "Temporary render context verification custody could not be released.",
            details={"recovery_required": True, "cleanup_errors": failures},
            recoverability="manual",
        )


def _verify_render_context_after_checkpoint(conn, expected: Dict[str, Any]) -> None:
    observed: Dict[str, Any] | None = None
    primary_error: Exception | None = None
    cleanup_errors: list[str] = []
    try:
        if expected.get("custody") == "render_preset_export":
            # Render presets live in DaVinci Resolve's global catalog, outside the
            # project DB checkpoint. Release the captured preset before taking
            # the post-restore catalog/context snapshot.
            _discard_render_context_preset_snapshot(conn, expected)
        observed = _snapshot_render_context(conn)
        if expected.get("custody") == "render_preset_export":
            keys = (
                "canonical_xml",
                "canonical_xml_sha256",
                "restore_settings",
                "format",
                "codec",
                "render_mode",
                "preset_catalog_before",
            )
        else:
            keys = ("settings", "format", "codec", "render_mode")
        differences = {}
        for key in keys:
            expected_value, observed_value = expected.get(key), observed.get(key)
            if expected_value == observed_value:
                continue
            if key == "canonical_xml":
                differences[key] = {
                    "expected_sha256": hashlib.sha256(
                        str(expected_value).encode()
                    ).hexdigest(),
                    "observed_sha256": hashlib.sha256(
                        str(observed_value).encode()
                    ).hexdigest(),
                }
            else:
                differences[key] = {
                    "expected": expected_value,
                    "observed": observed_value,
                }
        if differences:
            raise APICallFailed(
                "Full project checkpoint restore did not recover the exact render context.",
                details={"differences": differences},
                recoverability="manual",
            )
    except Exception as exc:
        primary_error = exc
    finally:
        for snapshot in (observed,):
            if (
                isinstance(snapshot, dict)
                and snapshot.get("custody") == "render_preset_export"
            ):
                try:
                    _discard_render_context_preset_snapshot(conn, snapshot)
                except Exception as exc:
                    cleanup_errors.append(str(exc))
    if cleanup_errors:
        raise APICallFailed(
            "Exact render context verification cleanup failed.",
            details={
                "error": str(primary_error) if primary_error else None,
                "cleanup_errors": cleanup_errors,
            },
            recoverability="manual",
        ) from primary_error
    if primary_error is not None:
        raise primary_error


def _restore_render_context(
    conn, snapshot: Dict[str, Any], *, require_deliver_page: bool = True
) -> None:
    if not isinstance(snapshot, dict):
        raise APICallFailed(
            "DaVinci Resolve render context cannot be restored from an invalid snapshot.",
            details={
                "recovery_required": True,
                "reason": "invalid_render_context_snapshot",
            },
            recoverability="manual",
        )

    if snapshot.get("custody") == "render_preset_export":
        _restore_render_context_from_preset(
            conn, snapshot, require_deliver_page=require_deliver_page
        )
        return

    restore_failures: list[Dict[str, Any]] = []
    try:
        with _with_required_page(conn, "deliver"):
            render_format = snapshot.get("format")
            render_codec = snapshot.get("codec")
            render_mode = snapshot.get("render_mode")
            if render_mode is not None:
                set_render_mode = _get_callable(
                    getattr(conn, "project", None), "SetCurrentRenderMode"
                )
                if set_render_mode is None:
                    restore_failures.append(
                        {"field": "render_mode", "reason": "setter_unavailable"}
                    )
                else:
                    try:
                        if set_render_mode(render_mode) is False:
                            restore_failures.append(
                                {
                                    "field": "render_mode",
                                    "reason": "setter_returned_false",
                                }
                            )
                    except Exception as exc:
                        restore_failures.append(
                            {
                                "field": "render_mode",
                                "reason": "setter_raised",
                                "error": str(exc),
                            }
                        )
            if render_format:
                set_format_and_codec = _get_callable(
                    getattr(conn, "project", None), "SetCurrentRenderFormatAndCodec"
                )
                if set_format_and_codec is None:
                    restore_failures.append(
                        {"field": "format_and_codec", "reason": "setter_unavailable"}
                    )
                else:
                    try:
                        if (
                            set_format_and_codec(render_format, render_codec or "")
                            is False
                        ):
                            restore_failures.append(
                                {
                                    "field": "format_and_codec",
                                    "reason": "setter_returned_false",
                                }
                            )
                    except Exception as exc:
                        restore_failures.append(
                            {
                                "field": "format_and_codec",
                                "reason": "setter_raised",
                                "error": str(exc),
                            }
                        )

            settings = snapshot.get("settings")
            if isinstance(settings, dict) and settings:
                set_settings = _get_callable(
                    getattr(conn, "project", None), "SetRenderSettings"
                )
                if set_settings is None:
                    restore_failures.append(
                        {"field": "settings", "reason": "setter_unavailable"}
                    )
                else:
                    try:
                        if set_settings(settings) is False:
                            restore_failures.append(
                                {"field": "settings", "reason": "setter_returned_false"}
                            )
                    except Exception as exc:
                        restore_failures.append(
                            {
                                "field": "settings",
                                "reason": "setter_raised",
                                "error": str(exc),
                            }
                        )
    except Exception as exc:
        restore_failures.append(
            {"field": "render_context", "reason": "restore_raised", "error": str(exc)}
        )

    observed = _snapshot_render_context(conn)
    mismatches: list[Dict[str, Any]] = []
    for field in ("format", "codec", "render_mode"):
        expected = snapshot.get(field)
        if expected is not None and observed.get(field) != expected:
            mismatches.append(
                {"field": field, "expected": expected, "observed": observed.get(field)}
            )
    expected_settings = snapshot.get("settings")
    observed_settings = observed.get("settings")
    if isinstance(expected_settings, dict) and expected_settings:
        if not isinstance(observed_settings, dict):
            mismatches.append(
                {
                    "field": "settings",
                    "expected": expected_settings,
                    "observed": observed_settings,
                }
            )
        else:
            for key, expected in expected_settings.items():
                if observed_settings.get(key) != expected:
                    mismatches.append(
                        {
                            "field": f"settings.{key}",
                            "expected": expected,
                            "observed": observed_settings.get(key),
                        }
                    )
    if mismatches:
        raise APICallFailed(
            "DaVinci Resolve render context could not be restored and verified.",
            details={
                "recovery_required": True,
                "restore_failures": restore_failures,
                "mismatches": mismatches,
            },
            recoverability="manual",
        )


def add_render_job(
    conn,
    mark_in: Optional[str] = None,
    mark_out: Optional[str] = None,
    range_domain: str = "record",
) -> str:
    preview = preview_add_render_job(conn, mark_in, mark_out, range_domain=range_domain)
    settings = preview["settings"]
    with _with_required_page(conn, "deliver"):
        set_settings = _get_callable(
            getattr(conn, "project", None), "SetRenderSettings"
        )
        if set_settings is None:
            raise APICallFailed(
                "SetRenderSettings not available.", details={"settings": settings}
            )
        set_result = set_settings(settings)
        if set_result is False:
            raise APICallFailed(
                "Failed to apply render settings before adding job.",
                details={"settings": settings},
            )

        job_id = _add_render_job_with_retry(
            conn,
            error_message="Failed to add render job.",
            details={
                "settings": settings,
                "queue_size_before": preview["queue_size_before"],
            },
        )
        return str(job_id)


def get_render_jobs(conn) -> List[Dict[str, Any]]:
    jobs = conn.project.GetRenderJobList()
    if not jobs:
        return []

    rows = []
    for job in jobs:
        if isinstance(job, dict):
            filename = ""
            for key in ("OutputFilename", "OutputFileName", "CustomName", "Filename"):
                value = job.get(key)
                if value is not None and str(value):
                    filename = value
                    break
            job_id = _render_job_id(job)
            dedicated = _read_render_job_status(conn, job_id) if job_id else None
            rows.append(
                {
                    "job_id": job.get("JobId", "?"),
                    "status": (
                        dedicated["status"]
                        if dedicated and dedicated["explicit"]
                        else job.get("RenderJobStatus", job.get("JobStatus", "?"))
                    ),
                    "progress": (
                        dedicated["progress"]
                        if dedicated and dedicated["explicit"]
                        else job.get("CompletionPercentage", 0)
                    ),
                    "target": job.get("TargetDir", ""),
                    "filename": filename,
                }
            )

    return rows


_RENDER_STATUS_KEYS = ("JobStatus", "RenderJobStatus", "Status", "status")
_RENDER_PROGRESS_KEYS = ("CompletionPercentage", "Progress", "progress")
_RENDER_COMPLETE_STATUSES = {"complete", "completed", "success", "succeeded"}
_RENDER_FAILED_STATUSES = {"failed", "error", "cancelled", "canceled", "aborted"}
_RENDER_STATUS_AMBIGUITY_TIMEOUT_S = 5.0
_RENDER_STATUS_STARTUP_TIMEOUT_S = 30.0


def _first_status_value(payload: Dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_render_job_status(payload: Any) -> Dict[str, Any]:
    raw = dict(payload) if isinstance(payload, dict) else {}
    status_value = _first_status_value(raw, _RENDER_STATUS_KEYS)
    progress_value = _first_status_value(raw, _RENDER_PROGRESS_KEYS)
    status = "" if status_value is None else str(status_value).strip()
    normalized = re.sub(r"[\s-]+", "_", status.casefold())
    try:
        progress = int(float(progress_value)) if progress_value is not None else 0
    except (TypeError, ValueError):
        progress = 0
    return {
        "status": status,
        "normalized_status": normalized,
        "progress": progress,
        "raw": raw,
        "explicit": bool(status),
    }


def _read_render_job_status(conn, job_id: str) -> Dict[str, Any]:
    getter = _get_callable(getattr(conn, "project", None), "GetRenderJobStatus")
    if getter is None:
        return {
            "available": False,
            "job_id": str(job_id),
            "status": "",
            "normalized_status": "",
            "progress": 0,
            "raw": {},
            "explicit": False,
            "error": "Project.GetRenderJobStatus is not available.",
        }
    try:
        payload = getter(str(job_id))
    except Exception as exc:
        return {
            "available": False,
            "job_id": str(job_id),
            "status": "",
            "normalized_status": "",
            "progress": 0,
            "raw": {},
            "explicit": False,
            "error": str(exc),
        }
    if not isinstance(payload, dict):
        return {
            "available": False,
            "job_id": str(job_id),
            "status": "",
            "normalized_status": "",
            "progress": 0,
            "raw": {},
            "explicit": False,
            "error": "Project.GetRenderJobStatus returned no status object.",
        }
    normalized = _normalize_render_job_status(payload)
    result = {"available": True, "job_id": str(job_id), **normalized}
    if not normalized["explicit"]:
        result["error"] = (
            "Project.GetRenderJobStatus did not include an explicit job status."
        )
    return result


def start_rendering(
    conn,
    jobs: Optional[str] = None,
    wait: bool = True,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> bool:
    list_jobs = _get_callable(getattr(conn, "project", None), "GetRenderJobList")
    set_settings = _get_callable(getattr(conn, "project", None), "SetRenderSettings")
    start_render = _get_callable(getattr(conn, "project", None), "StartRendering")
    if list_jobs is None or set_settings is None or start_render is None:
        raise APICallFailed("Render queue methods not available.")

    if _is_rendering_in_progress(conn):
        raise APICallFailed(
            "A render is already in progress.",
            details={
                "hint": "Wait for the active render or cancel it explicitly before starting another job."
            },
        )

    job_list = list_jobs() or []
    added_job_id: Optional[str] = None
    requested_job_ids = (
        [job_id.strip() for job_id in jobs.split(",") if job_id.strip()] if jobs else []
    )
    if jobs is not None and not requested_job_ids:
        raise ValidationError(
            "Render start job selector is empty.", details={"jobs": jobs}
        )

    if requested_job_ids:
        available_job_ids = {
            job_id for job_id in (_render_job_id(job) for job in job_list) if job_id
        }
        missing_job_ids = sorted(set(requested_job_ids) - available_job_ids)
        if missing_job_ids:
            raise ValidationError(
                "Render job not found.",
                details={
                    "requested_jobs": requested_job_ids,
                    "missing_jobs": missing_job_ids,
                    "available_jobs": [
                        _render_job_summary(job, index)
                        for index, job in enumerate(job_list, start=1)
                    ],
                    "hint": "Run `cutagent render jobs --json` and pass existing JobId values.",
                },
            )
    elif not job_list:
        settings_result = set_settings({"SelectAllFrames": True})
        if settings_result is False:
            raise APICallFailed(
                "Failed to configure a full-timeline render job.",
                details={"settings": {"SelectAllFrames": True}},
            )
        job_id = _add_render_job_with_retry(
            conn,
            error_message="No render jobs in queue and failed to add one.",
        )
        if not job_id:
            raise APICallFailed("No render jobs in queue and failed to add one.")
        added_job_id = str(job_id)

    wait_job_ids = requested_job_ids or (
        [added_job_id]
        if added_job_id is not None
        else [
            job_id
            for job_id in (_render_job_id(job) for job in (list_jobs() or []))
            if job_id
        ]
    )
    baseline_statuses = (
        {job_id: _read_render_job_status(conn, job_id) for job_id in wait_job_ids}
        if wait
        else {}
    )

    if requested_job_ids:
        start_result = start_render(requested_job_ids)
    else:
        start_result = start_render()
    if start_result is False:
        raise APICallFailed(
            "DaVinci Resolve rejected render start.",
            details={
                "requested_jobs": requested_job_ids or None,
                "available_jobs": [
                    _render_job_summary(job, index)
                    for index, job in enumerate(list_jobs() or [], start=1)
                ],
            },
        )

    if not wait:
        return True
    wait_for_render(
        conn,
        jobs=",".join(wait_job_ids),
        progress_callback=progress_callback,
        _baseline_statuses=baseline_statuses,
    )
    return True


def wait_for_render(
    conn,
    jobs: Optional[str] = None,
    timeout_s: Optional[float] = None,
    poll_ms: int = 500,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    _baseline_statuses: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if timeout_s is not None and timeout_s <= 0:
        raise ValidationError(
            "Render wait timeout must be positive.", details={"timeout_s": timeout_s}
        )
    if poll_ms <= 0:
        raise ValidationError(
            "Render wait poll interval must be positive.", details={"poll_ms": poll_ms}
        )

    job_filter = {j.strip() for j in jobs.split(",") if j.strip()} if jobs else None
    if jobs is not None and not job_filter:
        raise ValidationError(
            "Render wait job selector is empty.", details={"jobs": jobs}
        )

    initial_jobs = conn.project.GetRenderJobList() or []
    if not isinstance(initial_jobs, list):
        try:
            initial_jobs = list(initial_jobs)
        except Exception:
            initial_jobs = []

    if job_filter:
        available_job_ids = {
            job_id for job_id in (_render_job_id(job) for job in initial_jobs) if job_id
        }
        missing_jobs = sorted(job_filter - available_job_ids)
        if missing_jobs:
            raise ValidationError(
                "Render job not found.",
                details={
                    "requested_jobs": sorted(job_filter),
                    "missing_jobs": missing_jobs,
                    "available_jobs": [
                        _render_job_summary(job, index)
                        for index, job in enumerate(initial_jobs, start=1)
                    ],
                    "hint": "Run `cutagent render jobs --json` and pass existing JobId values.",
                },
            )
    else:
        job_filter = {
            job_id for job_id in (_render_job_id(job) for job in initial_jobs) if job_id
        }
        if not job_filter:
            raise APICallFailed(
                "Render status cannot be verified because the render queue has no job IDs.",
                details={
                    "required_api": "Project.GetRenderJobStatus",
                    "jobs": initial_jobs,
                },
            )

    deadline = (time.monotonic() + timeout_s) if timeout_s else None
    last_pct = 0
    last_status = "Unknown"
    ambiguous_since: Optional[float] = None
    last_job_statuses: list[Dict[str, Any]] = []
    require_post_start_evidence = _baseline_statuses is not None
    baseline_statuses = _baseline_statuses or {}
    status_transition_observed = {job_id: False for job_id in job_filter}
    post_start_nonterminal_observed = {job_id: False for job_id in job_filter}
    global_rendering_observed = False

    while True:
        cancellation_file = os.environ.get("CUTAGENT_CLI_SDK_CANCELLATION_FILE")
        if cancellation_file and Path(cancellation_file).is_file():
            if len(job_filter) != 1:
                raise APICallFailed(
                    "Render cancellation cannot safely stop multiple selected jobs.",
                    details={
                        "cancellation_requested": True,
                        "cancellation_acknowledged": False,
                        "requested_jobs": sorted(job_filter),
                    },
                    recoverability="manual",
                )
            cancelled_job_id = next(iter(job_filter))
            cancellation = cancel_render(
                conn,
                job_id=cancelled_job_id,
                require_exclusive_job=True,
            )
            if cancellation.get("cancelled") is not True:
                raise APICallFailed(
                    "Render cancellation was requested but no active render was stopped.",
                    details={
                        "cancellation_requested": True,
                        "cancellation_acknowledged": False,
                        "job_id": cancelled_job_id,
                    },
                    recoverability="manual",
                )
            raise APICallFailed(
                "Render cancellation was requested by the durable SDK operation.",
                details={
                    "cancellation_requested": True,
                    "cancellation_acknowledged": True,
                    "job_id": cancelled_job_id,
                },
                recoverability="retryable",
            )
        if deadline and time.monotonic() > deadline:
            raise APICallFailed(
                "Render wait timeout reached.",
                details={
                    "timeout_s": timeout_s,
                    "last_progress": last_pct,
                    "last_status": last_status,
                },
            )

        is_rendering = conn.project.IsRenderingInProgress()
        global_rendering_observed = global_rendering_observed or bool(is_rendering)
        last_job_statuses = [
            _read_render_job_status(conn, job_id) for job_id in sorted(job_filter)
        ]
        complete = []
        failed = []
        for job_status in last_job_statuses:
            status = str(job_status["status"])
            normalized_status = str(job_status["normalized_status"])
            pct = int(job_status["progress"])
            if progress_callback:
                progress_callback(pct, status)
            last_pct = pct
            last_status = status or "Unknown"
            job_id = str(job_status["job_id"])
            baseline = baseline_statuses.get(job_id)
            baseline_is_explicit = bool(baseline and baseline.get("explicit"))
            current_is_explicit = bool(job_status.get("explicit"))
            if (
                baseline_is_explicit
                and current_is_explicit
                and (
                    normalized_status != str(baseline.get("normalized_status") or "")
                    or pct != int(baseline.get("progress") or 0)
                )
            ):
                status_transition_observed[job_id] = True
            if (
                current_is_explicit
                and normalized_status not in _RENDER_COMPLETE_STATUSES
                and normalized_status not in _RENDER_FAILED_STATUSES
            ):
                post_start_nonterminal_observed[job_id] = True
            post_start_evidence = (
                not require_post_start_evidence
                or status_transition_observed[job_id]
                or post_start_nonterminal_observed[job_id]
                or (
                    len(job_filter) == 1
                    and global_rendering_observed
                    and not is_rendering
                )
            )
            if normalized_status in _RENDER_COMPLETE_STATUSES and post_start_evidence:
                complete.append(str(job_status["job_id"]))
            if normalized_status in _RENDER_FAILED_STATUSES and post_start_evidence:
                failed.append(job_status)

        if failed:
            raise APICallFailed(
                "Render failed.",
                details={"jobs": failed, "rendering": bool(is_rendering)},
            )
        if len(complete) == len(job_filter):
            return {"status": "complete", "progress": last_pct, "jobs": complete}

        unverifiable = any(
            not job_status["explicit"] for job_status in last_job_statuses
        )
        ambiguous = not is_rendering or unverifiable
        if ambiguous:
            now = time.monotonic()
            ambiguity_timeout_s = (
                _RENDER_STATUS_AMBIGUITY_TIMEOUT_S
                if unverifiable
                else _RENDER_STATUS_STARTUP_TIMEOUT_S
            )
            if ambiguous_since is None:
                ambiguous_since = now
            elif now - ambiguous_since >= ambiguity_timeout_s:
                raise APICallFailed(
                    "Render stopped without an explicit successful job status.",
                    details={
                        "jobs": last_job_statuses,
                        "rendering": False,
                        "ambiguity_timeout_s": ambiguity_timeout_s,
                        "require_post_start_evidence": require_post_start_evidence,
                        "global_rendering_observed": global_rendering_observed,
                        "status_transition_observed": status_transition_observed,
                        "post_start_nonterminal_observed": post_start_nonterminal_observed,
                        "hint": "Inspect the render job in DaVinci Resolve and verify the output artifact before retrying.",
                    },
                )
        else:
            ambiguous_since = None

        time.sleep(max(0.05, poll_ms / 1000.0))


def preview_cancel_render(
    conn, job_id: Optional[str] = None, delete_queued: bool = False
) -> Dict[str, Any]:
    resolved_job_id: Optional[str] = None
    jobs: List[Any] = []
    if job_id:
        resolved_job_id, jobs = _resolve_render_job_selector(conn, str(job_id))
    elif delete_queued:
        jobs = _get_render_jobs_for_delete(conn)

    queued_job_ids = [
        job_id_value
        for job_id_value in (_render_job_id(job) for job in jobs)
        if job_id_value is not None
    ]
    would_delete_jobs: list[str] = []
    if delete_queued:
        if resolved_job_id is not None:
            would_delete_jobs = [resolved_job_id]
        else:
            would_delete_jobs = queued_job_ids

    render_active = _is_rendering_in_progress(conn)
    return {
        "cancelled": False,
        "render_was_active": render_active,
        "would_cancel_active_render": render_active,
        "job_id": resolved_job_id if resolved_job_id is not None else job_id,
        "requested_job": job_id,
        "delete_queued": delete_queued,
        "would_delete_jobs": would_delete_jobs,
        "available_jobs": [
            _render_job_summary(job, index) for index, job in enumerate(jobs, start=1)
        ],
    }


def cancel_render(
    conn,
    job_id: Optional[str] = None,
    delete_queued: bool = False,
    require_exclusive_job: bool = False,
) -> Dict[str, Any]:
    preview = preview_cancel_render(conn, job_id=job_id, delete_queued=delete_queued)

    render_was_active = bool(preview["render_was_active"])
    resolved_job_id = str(preview["job_id"]) if preview["job_id"] is not None else None
    if require_exclusive_job:
        if not resolved_job_id:
            raise ValidationError(
                "Exclusive render cancellation requires one exact job ID."
            )
        available_ids = [
            value
            for value in (
                _render_job_id(job) for job in _get_render_jobs_for_delete(conn)
            )
            if value is not None
        ]
        statuses = [_read_render_job_status(conn, value) for value in available_ids]
        if any(
            not status["available"] or not status["explicit"] for status in statuses
        ):
            raise APICallFailed(
                "Exclusive render cancellation requires explicit status for every queued job.",
                details={"requested_job": resolved_job_id},
            )
        active_ids = [
            status["job_id"]
            for status in statuses
            if status["normalized_status"] in {"rendering", "in_progress"}
        ]
        render_was_active = _is_rendering_in_progress(conn)
        if not render_was_active or active_ids != [resolved_job_id]:
            raise APICallFailed(
                "Exclusive render cancellation requires global rendering and the requested job as the sole active render.",
                details={
                    "requested_job": resolved_job_id,
                    "rendering": render_was_active,
                    "active_jobs": active_ids,
                },
            )
    stopped = False
    exclusive_job_disappeared = False
    if render_was_active:
        stop_render = _get_callable(getattr(conn, "project", None), "StopRendering")
        if stop_render is None:
            raise APICallFailed(
                "StopRendering is not available.",
                details={"required_api": "Project.StopRendering"},
            )
        result = stop_render()
        if result is False:
            raise APICallFailed(
                "StopRendering returned false.",
                details={"api": "Project.StopRendering"},
            )
        stopped = True
        if require_exclusive_job:
            confirmed = _read_render_job_status(conn, resolved_job_id)
            cancellation_status = confirmed["normalized_status"] in {
                "cancelled",
                "canceled",
                "aborted",
            }
            remaining_ids = {
                value
                for value in (
                    _render_job_id(job) for job in _get_render_jobs_for_delete(conn)
                )
                if value is not None
            }
            disappeared = resolved_job_id not in remaining_ids
            if _is_rendering_in_progress(conn) or not (
                cancellation_status or disappeared
            ):
                raise APICallFailed(
                    "Exclusive render cancellation was not confirmed by native readback.",
                    details={
                        "requested_job": resolved_job_id,
                        "job_status": confirmed["normalized_status"],
                        "job_available": confirmed["available"],
                    },
                )
            exclusive_job_disappeared = disappeared

    deleted: list[str] = []
    if delete_queued:
        if job_id:
            resolved_job_id = str(preview["job_id"])
            if not (require_exclusive_job and exclusive_job_disappeared):
                delete_job = _get_callable(
                    getattr(conn, "project", None), "DeleteRenderJob"
                )
                if delete_job is None:
                    raise APICallFailed(
                        "DeleteRenderJob is not available.",
                        details={
                            "required_api": "Project.DeleteRenderJob",
                            "job_id": resolved_job_id,
                        },
                    )
                result = delete_job(resolved_job_id)
                if result is False:
                    raise APICallFailed(
                        "DeleteRenderJob returned false.",
                        details={
                            "api": "Project.DeleteRenderJob",
                            "job_id": resolved_job_id,
                        },
                    )
                deleted.append(resolved_job_id)
        else:
            if not preview["would_delete_jobs"]:
                return {
                    "cancelled": stopped,
                    "render_was_active": render_was_active,
                    "job_id": preview["job_id"],
                    "requested_job": job_id,
                    "delete_queued": delete_queued,
                    "deleted_jobs": deleted,
                    "available_jobs": preview["available_jobs"],
                }
            delete_all_jobs = _get_callable(
                getattr(conn, "project", None), "DeleteAllRenderJobs"
            )
            if delete_all_jobs is None:
                raise APICallFailed(
                    "DeleteAllRenderJobs is not available.",
                    details={"required_api": "Project.DeleteAllRenderJobs"},
                )
            result = delete_all_jobs()
            if result is False:
                raise APICallFailed(
                    "DeleteAllRenderJobs returned false.",
                    details={"api": "Project.DeleteAllRenderJobs"},
                )
            deleted = list(preview["would_delete_jobs"])

    available_jobs_after_delete = None
    if delete_queued:
        remaining_jobs = _get_render_jobs_for_delete(conn)
        remaining_job_ids = [
            value
            for value in (_render_job_id(job) for job in remaining_jobs)
            if value is not None
        ]
        available_jobs_after_delete = [
            _render_job_summary(job, index)
            for index, job in enumerate(remaining_jobs, start=1)
        ]
        remaining_deleted_jobs = [
            deleted_job_id
            for deleted_job_id in deleted
            if deleted_job_id in remaining_job_ids
        ]
        if remaining_deleted_jobs:
            raise APICallFailed(
                "Render queue delete reported success but job(s) are still present.",
                details={
                    "api": "Project.DeleteRenderJob"
                    if job_id
                    else "Project.DeleteAllRenderJobs",
                    "requested_job": job_id,
                    "deleted_jobs": deleted,
                    "remaining_deleted_jobs": remaining_deleted_jobs,
                    "available_jobs": available_jobs_after_delete,
                },
                recoverability="manual",
            )

    return {
        "cancelled": stopped,
        "render_was_active": render_was_active,
        "job_id": preview["job_id"],
        "requested_job": job_id,
        "delete_queued": delete_queued,
        "deleted_jobs": deleted,
        "available_jobs": preview["available_jobs"],
        "available_jobs_after_delete": available_jobs_after_delete,
        "exclusive_job_confirmed": require_exclusive_job,
    }


def render_custom_range(
    conn,
    mark_in: str,
    mark_out: str,
    *,
    start: bool = True,
    wait: bool = True,
    range_domain: str = "record",
) -> Dict[str, Any]:
    job_id = add_render_job(
        conn, mark_in=mark_in, mark_out=mark_out, range_domain=range_domain
    )
    result: Dict[str, Any] = {
        "job_id": job_id,
        "started": False,
        "waited": False,
        "range_domain": range_domain,
    }
    if start:
        start_render = _get_callable(getattr(conn, "project", None), "StartRendering")
        if start_render is None:
            raise APICallFailed(
                "StartRendering is not available.",
                details={"required_api": "Project.StartRendering", "job_id": job_id},
            )
        start_result = start_render([job_id])
        if start_result is False:
            raise APICallFailed(
                "Failed to start custom-range render job.",
                details={"api": "Project.StartRendering", "job_id": job_id},
            )
        result["started"] = True
        if wait:
            wait_for_render(conn, jobs=job_id)
            result["waited"] = True
    return result


def stop_rendering(conn) -> None:
    conn.project.StopRendering()


def get_render_status(conn, job_id: Optional[str] = None) -> Dict[str, Any]:
    is_rendering = conn.project.IsRenderingInProgress()
    result = {"rendering": is_rendering}

    jobs = conn.project.GetRenderJobList()
    if jobs:
        if job_id:
            resolved_job_id, jobs = _resolve_render_job_selector(conn, str(job_id))
        else:
            resolved_job_id = None
        job_info = []
        for job in jobs:
            if isinstance(job, dict):
                if resolved_job_id and _render_job_id(job) != resolved_job_id:
                    continue
                enriched = dict(job)
                current_job_id = _render_job_id(job)
                if current_job_id:
                    dedicated = _read_render_job_status(conn, current_job_id)
                    if dedicated["available"]:
                        enriched.update(dedicated["raw"])
                    if dedicated["explicit"]:
                        enriched["RenderJobStatus"] = dedicated["status"]
                        enriched["CompletionPercentage"] = dedicated["progress"]
                    enriched["cutagent_job_status"] = {
                        key: dedicated[key]
                        for key in (
                            "available",
                            "status",
                            "normalized_status",
                            "progress",
                            "error",
                        )
                        if key in dedicated
                    }
                job_info.append(enriched)
        result["jobs"] = job_info
    elif job_id:
        _resolve_render_job_selector(conn, str(job_id))

    return result


def _render_job_id(job: Any) -> Optional[str]:
    if isinstance(job, dict):
        for key in ("JobId", "JobID", "jobId", "job_id", "id"):
            value = job.get(key)
            if value is not None and str(value):
                return str(value)
    elif job is not None and str(job):
        return str(job)
    return None


def _render_job_summary(job: Any, index: int) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"index": index, "job_id": _render_job_id(job)}
    if not isinstance(job, dict):
        summary["raw"] = str(job)
        return summary

    field_map = {
        "status": ("RenderJobStatus", "JobStatus", "Status", "status"),
        "target_dir": ("TargetDir", "target_dir", "TargetDirectory"),
        "output_filename": (
            "OutputFilename",
            "OutputFileName",
            "CustomName",
            "Filename",
        ),
        "preset": ("PresetName", "RenderPreset", "preset"),
    }
    for out_key, candidate_keys in field_map.items():
        for candidate_key in candidate_keys:
            value = job.get(candidate_key)
            if value is not None and str(value):
                summary[out_key] = value
                break
    return summary


def _get_render_jobs_for_delete(conn) -> List[Any]:
    list_jobs = _get_callable(getattr(conn, "project", None), "GetRenderJobList")
    if list_jobs is None:
        raise APICallFailed(
            "GetRenderJobList is not available; cannot verify render queue before deleting.",
            details={
                "required_api": "Project.GetRenderJobList",
                "hint": "Use a DaVinci Resolve version that exposes render job IDs before deleting queue entries.",
            },
        )
    try:
        jobs = list_jobs() or []
    except Exception as exc:
        raise APICallFailed(
            "Failed to read render job list before deleting.",
            details={"api": "Project.GetRenderJobList", "error": str(exc)},
        ) from exc
    if not isinstance(jobs, list):
        try:
            jobs = list(jobs)
        except Exception:
            jobs = []
    return jobs


def _resolve_render_job_selector(conn, selector: str) -> tuple[str, List[Any]]:
    requested_job = str(selector)
    jobs = _get_render_jobs_for_delete(conn)

    for job in jobs:
        resolved_job_id = _render_job_id(job)
        if resolved_job_id == requested_job:
            return resolved_job_id, jobs

    if requested_job.isdecimal():
        queue_index = int(requested_job)
        if queue_index > 0 and queue_index <= len(jobs):
            indexed_job_id = _render_job_id(jobs[queue_index - 1])
            if indexed_job_id:
                return indexed_job_id, jobs

    raise ValidationError(
        "Render job not found.",
        details={
            "requested_job": requested_job,
            "available_jobs": [
                _render_job_summary(job, index)
                for index, job in enumerate(jobs, start=1)
            ],
            "hint": "Run `cutagent render jobs --json` and pass either the exact JobId or a 1-based queue index.",
        },
    )


def delete_render_job(
    conn, job_id: Optional[str] = None, all_jobs: bool = False
) -> Dict[str, Any]:
    if all_jobs:
        delete_all_jobs = _get_callable(
            getattr(conn, "project", None), "DeleteAllRenderJobs"
        )
        if delete_all_jobs is None:
            raise APICallFailed(
                "DeleteAllRenderJobs is not available.",
                details={"required_api": "Project.DeleteAllRenderJobs"},
            )
        result = delete_all_jobs()
        if result is False:
            raise APICallFailed(
                "DeleteAllRenderJobs returned false.",
                details={"api": "Project.DeleteAllRenderJobs"},
            )
        return {"deleted": True, "all": True}
    if job_id:
        resolved_job_id, jobs = _resolve_render_job_selector(conn, str(job_id))
        delete_job = _get_callable(getattr(conn, "project", None), "DeleteRenderJob")
        if delete_job is None:
            raise APICallFailed(
                "DeleteRenderJob is not available.",
                details={
                    "required_api": "Project.DeleteRenderJob",
                    "job_id": resolved_job_id,
                },
            )
        result = delete_job(resolved_job_id)
        if result is False:
            raise APICallFailed(
                "DeleteRenderJob returned false.",
                details={
                    "api": "Project.DeleteRenderJob",
                    "requested_job": str(job_id),
                    "resolved_job_id": resolved_job_id,
                    "available_jobs": [
                        _render_job_summary(job, index)
                        for index, job in enumerate(jobs, start=1)
                    ],
                },
            )
        return {
            "deleted": True,
            "job_id": resolved_job_id,
            "requested_job": str(job_id),
        }
    raise MissingArgumentError("Provide job_id or all_jobs=True.")


def render_audio(
    conn,
    output_path: str,
    format: str = "Wave",
    codec: str = "Linear PCM",
    bitdepth: int = 16,
    samplerate: int = 48000,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> str:
    bitdepth, samplerate = _validate_audio_render_settings(bitdepth, samplerate)
    _validate_audio_render_codec_request(conn, format=format, codec=codec)
    target_dir = _ensure_render_output_dir(output_path)
    base_name = os.path.splitext(os.path.basename(output_path))[0]
    snapshot = _snapshot_render_context(conn)
    job_id: str | None = None
    render_completed = False

    try:
        clear_and_refresh(conn)

        with _with_required_page(conn, "deliver"):
            resolved_format, resolved_codec = _set_audio_render_format_and_codec(
                conn, format_name=format, codec_name=codec
            )

            set_render_mode = _get_callable(
                getattr(conn, "project", None), "SetCurrentRenderMode"
            )
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
                "AudioBitDepth": bitdepth,
                "AudioSampleRate": samplerate,
            }

            set_settings = _get_callable(
                getattr(conn, "project", None), "SetRenderSettings"
            )
            if set_settings is None:
                raise APICallFailed(
                    "SetRenderSettings not available.", details={"settings": settings}
                )
            set_result = set_settings(settings)
            if set_result is False:
                raise APICallFailed(
                    "Failed to apply audio render settings.",
                    details={
                        "settings": settings,
                        "requested_format": format,
                        "requested_codec": codec,
                        "resolved_format": resolved_format,
                        "resolved_codec": resolved_codec,
                    },
                )

            job_id = str(
                _add_render_job_with_retry(
                    conn,
                    error_message="Failed to add audio render job.",
                    details={"settings": settings},
                )
            )

            if resolved_format == _AUDIO_ONLY_PRESET and resolved_codec == "":
                _verify_opaque_wave_pcm_job(
                    conn,
                    job_id=job_id,
                    target_dir=target_dir,
                    output_filename=os.path.basename(output_path),
                )

            _start_specific_render_job(
                conn,
                job_id,
                error_message="Failed to start audio render job.",
            )

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
                error_message="Render complete but output file not found at expected path.",
                job_id=job_id,
            )
    finally:
        if job_id is not None and not render_completed:
            _abort_render_job(conn, job_id=job_id)
        _restore_render_context(conn, snapshot)
