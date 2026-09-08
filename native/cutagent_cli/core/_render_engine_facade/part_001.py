"""Render engine — Render pipeline with retry, progress, cleanup."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import time
import uuid
from io import BytesIO
from contextlib import contextmanager
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import xml.etree.ElementTree as ET

from ..errors import APICallFailed, MissingArgumentError, ReadinessFailed, ValidationError
from ..utils.time_ref import parse_absolute_frame, parse_record_frame
from ._render_engine.common import _get_callable
from ._render_engine.preset_io import (
    _prepare_render_preset_export_path,
    _resolve_render_preset_import_path,
    export_burnin_preset,
    export_render_preset,
    import_burnin_preset,
    import_render_preset,
)
from ._render_engine.presets import (
    _normalize_render_preset_name,
    _render_preset_name,
    _render_preset_name_exists,
    _resolve_render_codec_selector,
    _resolve_render_format_selector,
    _resolve_render_preset_selector,
    _set_render_format_and_codec,
    _summarize_render_presets,
    get_render_codecs,
    get_render_formats,
    get_render_presets,
    get_render_resolutions,
    load_render_preset,
)
from ._render_engine.quick_export import (
    _quick_export_preset_name,
    _resolve_quick_export_output_path,
    _resolve_quick_export_preset_selector,
    _summarize_quick_export_presets,
    get_quick_export_presets,
    render_with_quick_export,
)

_COMPAT_EXPORTS = (
    _prepare_render_preset_export_path,
    _resolve_render_preset_import_path,
    export_burnin_preset,
    export_render_preset,
    import_burnin_preset,
    _normalize_render_preset_name,
    _render_preset_name,
    _render_preset_name_exists,
    _resolve_render_codec_selector,
    _resolve_render_format_selector,
    _resolve_render_preset_selector,
    _summarize_render_presets,
    get_render_codecs,
    get_render_formats,
    get_render_presets,
    get_render_resolutions,
    _quick_export_preset_name,
    _resolve_quick_export_output_path,
    _resolve_quick_export_preset_selector,
    _summarize_quick_export_presets,
    get_quick_export_presets,
    render_with_quick_export,
)

_RENDER_OUTPUT_EXTENSIONS = {
    ".aac",
    ".avi",
    ".braw",
    ".cin",
    ".dcp",
    ".dpx",
    ".exr",
    ".gif",
    ".j2c",
    ".jpg",
    ".m4a",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".mts",
    ".mxf",
    ".png",
    ".tif",
    ".tiff",
    ".wav",
    ".webm",
    ".webp",
}


def _xml_escape_text(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _xml_escape_attr(value: str) -> str:
    return _xml_escape_text(value).replace('"', "&quot;").replace("'", "&apos;")


def _replace_xml_root_attribute(xml_text: str, *, root_tag: str, attr_name: str, value: str) -> str:
    pattern = re.compile(rf"(<{re.escape(root_tag)}\b)([^>]*)(>)", re.DOTALL)
    match = pattern.search(xml_text)
    if not match:
        raise ValidationError(
            "Render preset XML is missing the expected root element.",
            details={"root_tag": root_tag},
        )

    attrs = match.group(2)
    escaped = _xml_escape_attr(value)
    attr_pattern = re.compile(rf"(\s{re.escape(attr_name)}\s*=\s*)([\"']).*?\2", re.DOTALL)
    if attr_pattern.search(attrs):
        attrs = attr_pattern.sub(lambda match: f'{match.group(1)}"{escaped}"', attrs, count=1)
    else:
        attrs = f'{attrs} {attr_name}="{escaped}"'
    return f"{xml_text[:match.start()]}{match.group(1)}{attrs}{match.group(3)}{xml_text[match.end():]}"


def _replace_xml_child_text(xml_text: str, *, root_tag: str, tag: str, value: str | None) -> str:
    escaped = "" if value is None else _xml_escape_text(value)
    replacement = f"<{tag}/>" if escaped == "" else f"<{tag}>{escaped}</{tag}>"
    paired_pattern = re.compile(rf"<{re.escape(tag)}\b[^>]*>.*?</{re.escape(tag)}>", re.DOTALL)
    if paired_pattern.search(xml_text):
        return paired_pattern.sub(lambda _match: replacement, xml_text, count=1)

    empty_pattern = re.compile(rf"<{re.escape(tag)}\b[^>]*/>", re.DOTALL)
    if empty_pattern.search(xml_text):
        return empty_pattern.sub(lambda _match: replacement, xml_text, count=1)

    close_pattern = re.compile(rf"</{re.escape(root_tag)}\s*>")
    close_match = close_pattern.search(xml_text)
    if not close_match:
        raise ValidationError(
            "Render preset XML is missing the expected closing root element.",
            details={"root_tag": root_tag, "tag": tag},
        )
    insert = f" <{tag}>{escaped}</{tag}>\n" if escaped else f" <{tag}/>\n"
    return f"{xml_text[:close_match.start()]}{insert}{xml_text[close_match.start():]}"


def _add_render_job_with_retry(
    conn,
    *,
    error_message: str,
    details: Optional[Dict[str, Any]] = None,
    attempts: int = 3,
    delay_s: float = 0.2,
):
    add_render_job = _get_callable(getattr(conn, "project", None), "AddRenderJob")
    if add_render_job is None:
        raise APICallFailed(
            "AddRenderJob not available.",
            details=dict(details or {}),
        )
    max_attempts = max(int(attempts), 1)
    for attempt in range(1, max_attempts + 1):
        job_id = add_render_job()
        if job_id:
            return job_id
        if attempt < max_attempts:
            time.sleep(delay_s)

    error_details = dict(details or {})
    error_details["add_job_attempts"] = max_attempts
    raise APICallFailed(error_message, details=error_details)


def _resolve_render_output_path(
    conn,
    *,
    target_dir: str,
    base_name: str,
    preferred_output_path: str,
    error_message: str,
    job_id: Optional[str] = None,
    settle_attempts: int = 12,
    settle_delay_s: float = 0.2,
) -> str:
    max_attempts = max(int(settle_attempts), 1)
    preferred_path = os.path.abspath(preferred_output_path)
    known_job_outputs: list[str] = []

    for attempt in range(1, max_attempts + 1):
        if os.path.exists(preferred_path):
            return preferred_path

        try:
            for job in conn.project.GetRenderJobList() or []:
                if not isinstance(job, dict):
                    continue
                if job_id is not None and str(job.get("JobId")) != str(job_id):
                    continue
                output_name = job.get("OutputFilename") or job.get("OutputFileName")
                if not output_name:
                    continue
                output_name = str(output_name)
                known_job_outputs.append(output_name)
                candidate = output_name if os.path.isabs(output_name) else os.path.join(target_dir, output_name)
                if os.path.exists(candidate):
                    return candidate
        except Exception:
            pass

        for ext in [".wav", ".mp3", ".aac", ".mov"]:
            alt_path = os.path.join(target_dir, base_name + ext)
            if os.path.exists(alt_path):
                return alt_path

        try:
            for candidate_name in os.listdir(target_dir):
                if not candidate_name.startswith(base_name + "."):
                    continue
                candidate_path = os.path.join(target_dir, candidate_name)
                if os.path.isfile(candidate_path) and Path(candidate_path).suffix.casefold() in _RENDER_OUTPUT_EXTENSIONS:
                    return candidate_path
        except Exception:
            pass

        if attempt < max_attempts:
            time.sleep(settle_delay_s)

    directory_listing: list[str] = []
    try:
        directory_listing = sorted(os.listdir(target_dir))
    except Exception:
        pass

    raise APICallFailed(
        error_message,
        details={
            "target_dir": target_dir,
            "base_name": base_name,
            "preferred_output_path": preferred_path,
            "job_id": None if job_id is None else str(job_id),
            "job_output_names": known_job_outputs,
            "directory_listing": directory_listing,
        },
    )


def clear_and_refresh(conn) -> None:
    """Clear the render queue and refresh connection state before render work."""
    if _is_rendering_in_progress(conn):
        _abort_render_job(conn)

    delete_all_jobs = _get_callable(getattr(conn, "project", None), "DeleteAllRenderJobs")
    list_jobs = _get_callable(getattr(conn, "project", None), "GetRenderJobList")
    delete_job = _get_callable(getattr(conn, "project", None), "DeleteRenderJob")

    if delete_all_jobs is not None:
        try:
            delete_all_jobs()
        except Exception:
            pass

        if list_jobs is not None:
            try:
                jobs = list_jobs()
            except Exception:
                jobs = []
            if jobs:
                for job in jobs:
                    job_id = job.get("JobId") if isinstance(job, dict) else job
                    if job_id and delete_job is not None:
                        try:
                            delete_job(job_id)
                        except Exception:
                            pass

    conn.refresh()
    if _is_rendering_in_progress(conn):
        raise APICallFailed("DaVinci Resolve still reports an active render after cleanup.")


def _is_rendering_in_progress(conn) -> bool:
    getter = _get_callable(getattr(conn, "project", None), "IsRenderingInProgress")
    if getter is None:
        return False
    try:
        return bool(getter())
    except Exception:
        return False


def _abort_render_job(
    conn,
    *,
    job_id: Optional[str] = None,
    attempts: int = 5,
    delay_s: float = 0.1,
) -> None:
    project = getattr(conn, "project", None)
    if project is None:
        return

    stop_render = _get_callable(project, "StopRendering")
    delete_job = _get_callable(project, "DeleteRenderJob")
    delete_all_jobs = _get_callable(project, "DeleteAllRenderJobs")
    list_jobs = _get_callable(project, "GetRenderJobList")

    try:
        with _with_required_page(conn, "deliver"):
            for _attempt in range(max(int(attempts), 1)):
                if not _is_rendering_in_progress(conn):
                    break
                if stop_render is not None:
                    try:
                        stop_render()
                    except Exception:
                        pass
                time.sleep(max(delay_s, 0.01))
    except Exception:
        pass

    if job_id and delete_job is not None:
        try:
            delete_job(str(job_id))
        except Exception:
            pass
    elif delete_all_jobs is not None:
        try:
            delete_all_jobs()
        except Exception:
            pass
    elif delete_job is not None and list_jobs is not None:
        try:
            for job in list_jobs() or []:
                if not isinstance(job, dict):
                    continue
                existing_job_id = job.get("JobId")
                if existing_job_id is None:
                    continue
                try:
                    delete_job(str(existing_job_id))
                except Exception:
                    pass
        except Exception:
            pass


@contextmanager
def _with_required_page(conn, page: str):
    resolve = getattr(conn, "resolve", None)
    open_page = _get_callable(resolve, "OpenPage")
    get_current_page = _get_callable(resolve, "GetCurrentPage")
    previous_page: Optional[str] = None
    switched = False

    if get_current_page is not None:
        try:
            previous_page = get_current_page()
        except Exception:
            previous_page = None

    if resolve and previous_page != page:
        if open_page is None:
            raise APICallFailed(
                "OpenPage not available.",
                details={"required_page": page, "current_page": previous_page},
            )
        opened = open_page(page)
        if opened is False:
            raise APICallFailed(
                f"Failed to switch DaVinci Resolve to '{page}' page.",
                details={"required_page": page, "current_page": previous_page},
            )
        switched = True
        time.sleep(0.05)

    try:
        yield
    finally:
        if switched and open_page is not None and previous_page and previous_page != page:
            try:
                open_page(previous_page)
            except Exception:
                pass


def _ensure_render_output_dir(output_path: str) -> str:
    target_dir = os.path.dirname(os.path.abspath(output_path))
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as exc:
        raise ValidationError(
            "Render output directory is not writable.",
            details={"output_path": output_path, "target_dir": target_dir, "error": str(exc)},
        ) from exc
    return target_dir


def _validate_audio_render_settings(bitdepth: int, samplerate: int) -> tuple[int, int]:
    try:
        resolved_bitdepth = int(bitdepth)
        resolved_samplerate = int(samplerate)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Audio render settings must be numeric.",
            details={"bitdepth": bitdepth, "samplerate": samplerate},
        ) from exc
    if resolved_bitdepth <= 0 or resolved_samplerate <= 0:
        raise ValidationError(
            "Audio render settings must be positive.",
            details={"bitdepth": resolved_bitdepth, "samplerate": resolved_samplerate},
        )
    return resolved_bitdepth, resolved_samplerate


def _validate_audio_render_codec_request(conn, *, format: str, codec: str) -> None:
    project = getattr(conn, "project", None)
    if not callable(getattr(project, "GetRenderFormats", None)):
        return
    resolved_format, _ = _resolve_render_format_selector(conn, format)
    try:
        available_codecs = get_render_codecs(conn, resolved_format)
    except APICallFailed:
        return
    # An empty codec map is not proof that the format is unavailable. DaVinci
    # Resolve can expose audio-only output exclusively through its built-in
    # preset while returning no codecs for Wave. The render setup below must
    # resolve that preset-backed route (or fail on the native setter) instead
    # of rejecting it during preflight.
    if not available_codecs:
        return


def _start_specific_render_job(
    conn,
    job_id: str,
    *,
    error_message: str,
    allow_start_all_fallback: bool = True,
    attempts: int = 5,
    delay_s: float = 0.2,
) -> None:
    start_render = _get_callable(getattr(conn, "project", None), "StartRendering")
    if start_render is None:
        raise APICallFailed("StartRendering not available.")

    attempted_signatures: list[str] = []
    signatures = [
        ("StartRendering(jobId)", (job_id,)),
        ("StartRendering([jobId])", ([job_id],)),
    ]
    if allow_start_all_fallback:
        signatures.append(("StartRendering()", ()))

    max_attempts = max(int(attempts), 1)
    last_jobs: list[Any] = []
    for attempt in range(1, max_attempts + 1):
        last_jobs = _get_render_jobs_safely(conn)
        for signature, args in signatures:
            attempted_signatures.append(signature)
            try:
                result = start_render(*args)
            except TypeError:
                continue
            if result is False:
                continue
            return
        if attempt < max_attempts:
            time.sleep(delay_s)

    raise APICallFailed(
        error_message,
        details={
            "job_id": job_id,
            "attempted_signatures": attempted_signatures,
            "start_attempts": max_attempts,
            "render_jobs": last_jobs,
        },
    )


def _method_unavailable_error(exc: Exception) -> bool:
    return "method not available" in str(exc).lower()


def _label_for_render_format(conn, format_value: Any) -> Optional[str]:
    if format_value in (None, ""):
        return None
    requested = str(format_value)
    try:
        formats = get_render_formats(conn)
    except Exception:
        return None
    requested_casefold = requested.casefold().lstrip(".")
    for label, value in formats.items():
        if str(label) == requested:
            return str(label)
        if str(value) == requested:
            return str(label)
        if str(label).casefold() == requested_casefold:
            return str(label)
        if str(value).casefold().lstrip(".") == requested_casefold:
            return str(label)
    return None


def _label_for_render_codec(conn, format_label_or_value: Any, codec_value: Any) -> Optional[str]:
    if format_label_or_value in (None, "") or codec_value in (None, ""):
        return None
    requested = str(codec_value)
    try:
        codecs = get_render_codecs(conn, str(format_label_or_value))
    except Exception:
        return None
    requested_casefold = requested.casefold()
    for label, value in codecs.items():
        if str(label) == requested:
            return str(label)
        if str(value) == requested:
            return str(label)
        if str(label).casefold() == requested_casefold:
            return str(label)
        if str(value).casefold() == requested_casefold:
            return str(label)
    return None


def _render_mode_description(mode: Any) -> str:
    if mode == 0:
        return "individual"
    if mode == 1:
        return "single"
    return f"unknown ({mode})"


_PROJECT_RENDER_CONTEXT_SETTINGS = {
    "timeline_resolution_width": "timelineResolutionWidth",
    "timeline_resolution_height": "timelineResolutionHeight",
    "timeline_output_resolution_width": "timelineOutputResolutionWidth",
    "timeline_output_resolution_height": "timelineOutputResolutionHeight",
    "timeline_output_resolution_matches_timeline": "timelineOutputResMatchTimelineRes",
    "timeline_frame_rate": "timelineFrameRate",
    "timeline_playback_frame_rate": "timelinePlaybackFrameRate",
    "video_data_levels": "videoDataLevels",
    "video_monitor_format": "videoMonitorFormat",
}


def _burnin_preset_settings_paths() -> List[Path]:
    """Return known DaVinci Resolve settings files that store user data burn-in presets."""
    relative_candidates = (
        Path("Library/Application Support/Blackmagic Design/DaVinci Resolve/Resolve Project Library/Resolve Projects/Settings/SlatePresetList.xml"),
        Path("Library/Application Support/Blackmagic Design/DaVinci Resolve/Support/Resolve Project Library/Resolve Projects/Settings/SlatePresetList.xml"),
    )
    paths = [Path.home() / relative for relative in relative_candidates]
    paths.append(
        Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Resolve Project Library/Resolve Projects/Settings/SlatePresetList.xml")
    )
    return paths


def _extract_burnin_preset_names_from_xml(path: Path) -> List[str]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return []

    names: List[str] = []
    seen: set[str] = set()
    name_attr_keys = ("Name", "name", "PresetName", "presetName", "Preset Name", "preset_name")
    name_tags = {"name", "presetname", "preset_name", "preset"}

    def add_name(value: Any) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        normalized = _normalize_render_preset_name(text)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        names.append(text)

    def local_tag(element: ET.Element) -> str:
        return element.tag.split("}", 1)[-1].casefold()

    # DaVinci Resolve 21 stores user presets as keyed values rather than named
    # ``Preset`` nodes.  Only accept a DbKey from the exact PresetList/Element
    # record shape, paired with a DbVal sibling, so unrelated database keys in
    # the settings document cannot become selectable preset names.
    for preset_list in root.iter():
        if local_tag(preset_list) != "presetlist":
            continue
        for record in preset_list:
            if local_tag(record) != "element":
                continue
            children = {local_tag(child): child for child in record}
            if "dbkey" in children and "dbval" in children:
                add_name(children["dbkey"].text)

    for element in root.iter():
        for key in name_attr_keys:
            add_name(element.attrib.get(key))

        tag = local_tag(element)
        if tag in name_tags:
            add_name(element.text)

        if "preset" in tag:
            for key, value in element.attrib.items():
                if "name" in key.casefold():
                    add_name(value)

    return names


def get_burnin_presets() -> List[Dict[str, Any]]:
    """List user-defined data burn-in presets visible in DaVinci Resolve's settings catalog."""
    presets: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for path in _burnin_preset_settings_paths():
        exists = path.exists()
        names = _extract_burnin_preset_names_from_xml(path) if exists else []
        for name in names:
            normalized = _normalize_render_preset_name(name)
            if normalized in seen:
                continue
            seen.add(normalized)
            presets.append({"index": len(presets) + 1, "name": name, "settings_path": str(path)})
    return presets


def _summarize_burnin_presets(presets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"index": preset.get("index"), "name": preset.get("name")} for preset in presets]


def _burnin_preset_not_found_error(
    requested_preset: str,
    presets: List[Dict[str, Any]],
    *,
    built_in_hint: bool = False,
    attempted_exact_load: bool = False,
) -> ValidationError:
    names = [str(preset["name"]) for preset in presets if preset.get("name")]
    hint = "Create or import a user data burn-in preset in DaVinci Resolve, then pass that exact preset name."
    if built_in_hint:
        hint = (
            "`None` and `Same as project` are built-in UI choices, not user-defined data burn-in presets accepted by "
            "DaVinci Resolve's LoadBurnInPreset API."
        )
    return ValidationError(
        "Burn-in preset not found.",
        details={
            "requested_preset": requested_preset,
            "available_presets": _summarize_burnin_presets(presets),
            "suggestions": get_close_matches(requested_preset, names, n=5, cutoff=0.45),
            "detected_settings_paths": [str(path) for path in _burnin_preset_settings_paths() if path.exists()],
            "attempted_exact_load": attempted_exact_load,
            "hint": hint,
        },
    )


def _resolve_burnin_preset_selector(
    selector: str,
    *,
    allow_unlisted_exact: bool = False,
) -> tuple[str, List[Dict[str, Any]], bool]:
    requested_preset = str(selector).strip()
    presets = get_burnin_presets()
    names = [str(preset["name"]) for preset in presets if preset.get("name")]

    for name in names:
        if name == requested_preset:
            return name, presets, False

    requested_casefold = requested_preset.casefold()
    case_matches = [name for name in names if name.casefold() == requested_casefold]
    if len(case_matches) == 1:
        return case_matches[0], presets, False
    if len(case_matches) > 1:
        raise ValidationError(
            "Burn-in preset selector is ambiguous.",
            details={
                "requested_preset": requested_preset,
                "matches": case_matches,
                "available_presets": _summarize_burnin_presets(presets),
                "hint": "Pass the exact data burn-in preset name from DaVinci Resolve's Data Burn-In dialog.",
            },
        )

    requested_normalized = _normalize_render_preset_name(requested_preset)
    normalized_matches = [name for name in names if _normalize_render_preset_name(name) == requested_normalized]
    if len(normalized_matches) == 1:
        return normalized_matches[0], presets, False
    if len(normalized_matches) > 1:
        raise ValidationError(
            "Burn-in preset selector is ambiguous.",
            details={
                "requested_preset": requested_preset,
                "matches": normalized_matches,
                "available_presets": _summarize_burnin_presets(presets),
                "hint": "Pass the exact data burn-in preset name from DaVinci Resolve's Data Burn-In dialog.",
            },
        )

    if requested_preset.isdecimal():
        preset_index = int(requested_preset)
        if 0 < preset_index <= len(names):
            return names[preset_index - 1], presets, False

    partial_matches = [
        name for name in names if requested_normalized and requested_normalized in _normalize_render_preset_name(name)
    ]
    if len(partial_matches) == 1:
        return partial_matches[0], presets, False
    if len(partial_matches) > 1:
        raise ValidationError(
            "Burn-in preset selector is ambiguous.",
            details={
                "requested_preset": requested_preset,
                "matches": partial_matches,
                "available_presets": _summarize_burnin_presets(presets),
                "hint": "Multiple data burn-in presets match this selector; pass an exact preset name or 1-based index.",
            },
        )

    built_in_names = {"none", "sameasproject"}
    if allow_unlisted_exact and requested_normalized not in built_in_names:
        return requested_preset, presets, True
    raise _burnin_preset_not_found_error(
        requested_preset,
        presets,
        built_in_hint=requested_normalized in built_in_names,
    )


def _get_project_setting_value(project: Any, key: str) -> Any:
    get_setting = _get_callable(project, "GetSetting")
    if get_setting is None:
        return None
    try:
        return get_setting(key)
    except Exception:
        return None


def get_render_settings(conn) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    source: Dict[str, Any] = {
        "get_render_settings": "unavailable",
        "current_format_codec": "unavailable",
        "current_render_mode": "unavailable",
        "render_queue": "unavailable",
    }

    try:
        getter = getattr(conn.project, "GetRenderSettings", None)
        if getter is not None and callable(getter):
            settings = getter()
            if isinstance(settings, dict):
                result.update(settings)
                source["get_render_settings"] = "available"
            else:
                source["get_render_settings"] = "non_dict"
        else:
            source["get_render_settings"] = "missing"
    except APICallFailed as exc:
        if not _method_unavailable_error(exc):
            raise
        source["get_render_settings"] = "method_not_available"
    except (TypeError, AttributeError):
        source["get_render_settings"] = "missing"

    try:
        fmt_codec = conn.project.GetCurrentRenderFormatAndCodec()
        if isinstance(fmt_codec, dict):
            result.update(fmt_codec)
            source["current_format_codec"] = "available"
            format_value = (
                result.get("format")
                or result.get("Format")
                or result.get("format_name")
                or result.get("FormatName")
            )
            codec_value = (
                result.get("codec")
                or result.get("Codec")
                or result.get("codec_name")
                or result.get("CodecName")
            )
            format_label = _label_for_render_format(conn, format_value)
            if format_label:
                result["format_label"] = format_label
            codec_label = _label_for_render_codec(conn, format_label or format_value, codec_value)
            if codec_label:
                result["codec_label"] = codec_label
        else:
            source["current_format_codec"] = "non_dict"
    except Exception:
        source["current_format_codec"] = "unavailable"

    try:
        get_render_mode = _get_callable(getattr(conn, "project", None), "GetCurrentRenderMode")
        if get_render_mode is not None:
            render_mode = get_render_mode()
            result["render_mode"] = render_mode
            result["render_mode_description"] = _render_mode_description(render_mode)
            source["current_render_mode"] = "available"
    except Exception:
        source["current_render_mode"] = "unavailable"

    try:
        list_jobs = _get_callable(getattr(conn, "project", None), "GetRenderJobList")
        if list_jobs is not None:
            jobs = list_jobs()
            result["render_queue_count"] = len(jobs) if isinstance(jobs, list) else 0
            source["render_queue"] = "available"
    except Exception:
        source["render_queue"] = "unavailable"

    project = getattr(conn, "project", None)
    for output_key, project_key in _PROJECT_RENDER_CONTEXT_SETTINGS.items():
        if output_key in result:
            continue
        value = _get_project_setting_value(project, project_key)
        if value not in (None, ""):
            result[output_key] = value

    result["settings_api_available"] = source.get("get_render_settings") == "available"
    result["source"] = source
    return result


def preflight_audio_render(
    conn,
    *,
    format: str = "Wave",
    codec: str = "Linear PCM",
) -> Dict[str, Any]:
    """Verify that DaVinci Resolve exposes the audio render format/codec before switching pages."""
    resolved_format, available_formats = _resolve_render_format_selector(conn, format)
    try:
        available_codecs = get_render_codecs(conn, resolved_format)
    except APICallFailed as exc:
        raise ReadinessFailed(
            "Audio render codec list is unavailable.",
            details={
                "requested_format": format,
                "requested_codec": codec,
                "resolved_format": resolved_format,
                "available_formats": available_formats,
                "error": str(exc),
            },
        ) from exc

    if not available_codecs:
        raise ReadinessFailed(
            "Audio render codec is unavailable for the requested format.",
            details={
                "requested_format": format,
                "requested_codec": codec,
                "resolved_format": resolved_format,
                "available_formats": available_formats,
                "available_codecs": available_codecs,
                "hint": "DaVinci Resolve did not expose any Wave codecs. Use `cutagent render codecs Wave -j` to verify render support before running silence-cut.",
            },
        )

    resolved_codec, _ = _resolve_render_codec_selector(
        conn,
        format_name=resolved_format,
        codec_name=codec,
    )
    return {
        "format": resolved_format,
        "codec": resolved_codec,
        "available_formats": available_formats,
        "available_codecs": available_codecs,
    }


_RENDER_TARGET_KEYS = ("TargetDir", "targetDir", "TargetDirectory", "target_directory")
_RENDER_NAME_KEYS = ("CustomName", "customName", "OutputFilename", "OutputFileName", "output_filename")


def _first_render_setting(settings: Dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = settings.get(key)
        if value not in (None, ""):
            return value
    return None


def _render_settings_for_add_precondition(conn) -> tuple[Dict[str, Any], bool]:
    getter = getattr(conn.project, "GetRenderSettings", None)
    if getter is not None and callable(getter):
        try:
            settings = getter()
            if isinstance(settings, dict):
                return settings, True
        except APICallFailed as exc:
            if "method not available" not in str(exc).lower():
                raise
        except (TypeError, AttributeError):
            pass
    return get_render_settings(conn), False


def _render_job_settings(
    conn,
    mark_in: Optional[str] = None,
    mark_out: Optional[str] = None,
    range_domain: str = "record",
) -> Dict[str, Any]:
    if mark_in or mark_out:
        try:
            start_frame = int(conn.timeline.GetStartFrame())
        except Exception:
            start_frame = int(getattr(conn, "start_frame", 0) or 0)

        domain = str(range_domain or "record").strip().lower().replace("_", "-")
        if domain in {"absolute-record", "timeline", "absolute-timeline"}:
            domain = "absolute"
        if domain not in {"record", "absolute"}:
            raise ValidationError(
                "Render range domain must be 'record' or 'absolute'.",
                details={"range_domain": range_domain, "supported": ["record", "absolute"]},
            )

        def _parse_mark(raw: str) -> int:
            if domain == "absolute":
                return parse_absolute_frame(raw, conn.fps)
            return parse_record_frame(raw, conn.fps, start_frame)

        settings: Dict[str, Any] = {"SelectAllFrames": False}
        if mark_in:
            settings["MarkIn"] = _parse_mark(mark_in)
        if mark_out:
            settings["MarkOut"] = _parse_mark(mark_out)
        if "MarkIn" in settings and "MarkOut" in settings and int(settings["MarkIn"]) > int(settings["MarkOut"]):
            raise ValidationError(
                "Render in point must be before or equal to out point.",
                details={
                    "mark_in": mark_in,
                    "mark_out": mark_out,
                    "range_domain": domain,
                    "mark_in_frame": settings["MarkIn"],
                    "mark_out_frame": settings["MarkOut"],
                },
            )
        return settings
    return {"SelectAllFrames": True}
