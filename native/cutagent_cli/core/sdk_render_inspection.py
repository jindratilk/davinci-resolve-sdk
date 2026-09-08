"""Private bounded render-state carrier for the public CutAgent SDK."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List

from .sdk_live_inspection import documented_unique_id, validate_deadline


MAX_RENDER_FORMATS = 256
MAX_RENDER_CODECS_PER_FORMAT = 256
MAX_RENDER_RESOLUTIONS_PER_CODEC = 512
MAX_RENDER_PRESETS = 2048
MAX_RENDER_QUEUE_JOBS = 10_000
MAX_RENDER_LABEL_LENGTH = 1024


def _safe_call(target: Any, method: str, *args: Any) -> tuple[str, Any]:
    callback = getattr(target, method, None)
    if not callable(callback):
        return "unavailable", None
    try:
        return "supported", callback(*args)
    except Exception:
        return "unavailable", None


def _bounded_list(value: Any, maximum: int) -> tuple[str, List[Any]]:
    if value is None:
        return "unknown_version", []
    if not isinstance(value, list):
        return "unknown_version", []
    if len(value) > maximum:
        return "unknown_version", []
    return "supported", value


def _bounded_dict(value: Any, maximum: int) -> tuple[str, Dict[Any, Any]]:
    if value is None:
        return "unknown_version", {}
    if not isinstance(value, dict):
        return "unknown_version", {}
    if len(value) > maximum:
        return "unknown_version", {}
    return "supported", value


def _carrier_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_RENDER_LABEL_LENGTH or "\x00" in normalized:
        return None
    return normalized


def _canonical_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else None
    if isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
        return int(value)
    return None


def _resolution(value: Any) -> Dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    width = value.get("Width", value.get("width"))
    height = value.get("Height", value.get("height"))
    width_value = _canonical_int(width)
    height_value = _canonical_int(height)
    if width_value is None or height_value is None:
        return None
    if not (0 < width_value <= 65_536 and 0 < height_value <= 65_536):
        return None
    return {"width": width_value, "height": height_value}


def _raw_render_formats(project: Any) -> tuple[str, Dict[Any, Any]]:
    support, value = _safe_call(project, "GetRenderFormats")
    if support != "supported":
        return support, {}
    return _bounded_dict(value, MAX_RENDER_FORMATS)


def _raw_render_codecs(
    project: Any,
    format_label: Any,
    extension: Any,
) -> tuple[str, Dict[Any, Any]]:
    candidates = [format_label]
    if extension is not None and extension not in candidates:
        candidates.append(extension)
    saw_supported = False
    saw_unknown = False
    for candidate in candidates:
        support, value = _safe_call(project, "GetRenderCodecs", candidate)
        if support == "unavailable":
            return support, {}
        shape_support, codecs = _bounded_dict(value, MAX_RENDER_CODECS_PER_FORMAT)
        if shape_support == "unknown_version":
            saw_unknown = True
            continue
        saw_supported = True
        if codecs:
            return "supported", codecs
    return ("supported" if saw_supported else "unknown_version" if saw_unknown else "supported"), {}


def _raw_render_resolutions(
    project: Any,
    format_label: Any,
    extension: Any,
    codec_value: Any,
) -> tuple[str, List[Any]]:
    candidates = [format_label]
    if extension is not None and extension not in candidates:
        candidates.append(extension)
    saw_supported = False
    saw_unknown = False
    for candidate in candidates:
        support, value = _safe_call(
            project,
            "GetRenderResolutions",
            candidate,
            codec_value,
        )
        if support == "unavailable":
            return support, []
        shape_support, resolutions = _bounded_list(
            value,
            MAX_RENDER_RESOLUTIONS_PER_CODEC,
        )
        if shape_support == "unknown_version":
            saw_unknown = True
            continue
        saw_supported = True
        if resolutions:
            return "supported", resolutions
    return ("supported" if saw_supported else "unknown_version" if saw_unknown else "supported"), []


def _render_discovery(conn: Any, deadline_at_ms: int) -> Dict[str, Any]:
    project = getattr(conn, "project", None)
    format_support, formats = _raw_render_formats(project)
    rows: List[Dict[str, Any]] = []
    normalized_formats: List[tuple[str, str | None]] = []
    for raw_label, raw_extension in formats.items():
        format_label = _carrier_label(raw_label)
        extension = None if raw_extension is None else _carrier_label(raw_extension)
        if format_label is None or (raw_extension is not None and extension is None):
            return {"format_support": "unknown_version", "formats": []}
        normalized_formats.append((format_label, extension))
    for format_label, extension in sorted(normalized_formats, key=lambda item: item[0].casefold()):
        validate_deadline(deadline_at_ms)
        codec_support, codecs = _raw_render_codecs(project, format_label, extension)
        codec_rows: List[Dict[str, Any]] = []
        normalized_codecs: List[tuple[str, str]] = []
        for raw_label, raw_value in codecs.items():
            codec_label = _carrier_label(raw_label)
            codec_value = _carrier_label(raw_value)
            if codec_label is None or codec_value is None:
                codec_support = "unknown_version"
                normalized_codecs = []
                break
            normalized_codecs.append((codec_label, codec_value))
        for codec_label, codec_value in sorted(normalized_codecs, key=lambda item: item[0].casefold()):
            validate_deadline(deadline_at_ms)
            resolution_support, resolutions = _raw_render_resolutions(
                project,
                format_label,
                extension,
                codec_value,
            )
            normalized_resolutions: List[Dict[str, int]] = []
            if resolution_support == "supported":
                for raw_resolution in resolutions:
                    normalized = _resolution(raw_resolution)
                    if normalized is None:
                        resolution_support = "unknown_version"
                        normalized_resolutions = []
                        break
                    if normalized not in normalized_resolutions:
                        normalized_resolutions.append(normalized)
            codec_rows.append(
                {
                    "label": codec_label,
                    "api_value": codec_value,
                    "resolution_support": resolution_support,
                    "resolutions": normalized_resolutions,
                }
            )
        rows.append(
            {
                "label": format_label,
                "extension": extension,
                "codec_support": codec_support,
                "codecs": codec_rows,
            }
        )
    return {"format_support": format_support, "formats": rows}


def _render_presets(conn: Any) -> Dict[str, Any]:
    support, value = _safe_call(getattr(conn, "project", None), "GetRenderPresetList")
    if support == "supported":
        support, values = _bounded_list(value, MAX_RENDER_PRESETS)
    else:
        values = []
    names: List[str] = []
    if support == "supported":
        for value in values:
            name = value if isinstance(value, str) else None
            if not name or not name.strip() or len(name.strip()) > 1024:
                support = "unknown_version"
                names = []
                break
            names.append(name.strip())
    return {"support": support, "presets": names}


def _render_settings(project: Any) -> Dict[str, Any]:
    support, settings = _safe_call(project, "GetRenderSettings")
    if support == "supported" and not isinstance(settings, dict):
        support, settings = "unknown_version", {}
    elif not isinstance(settings, dict):
        settings = {}
    format_support, format_codec = _safe_call(project, "GetCurrentRenderFormatAndCodec")
    if format_support != "supported" or not isinstance(format_codec, dict):
        format_codec = {}
    return {
        "support": support,
        "settings": settings,
        "format_codec": format_codec,
        # GetCurrentRenderMode activates the Deliver page on DaVinci Resolve
        # Studio 21. A semantic read must not depend on cleanup after a killed
        # process, so this side-effecting getter is deliberately excluded.
        "mode": None,
    }


def _job_id(job: Dict[str, Any]) -> str | None:
    for key in ("JobId", "JobID", "job_id"):
        value = job.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _render_jobs(project: Any, deadline_at_ms: int) -> Dict[str, Any]:
    support, raw_jobs = _safe_call(project, "GetRenderJobList")
    if support != "supported":
        return {"support": support, "jobs": []}
    support, jobs = _bounded_list(raw_jobs, MAX_RENDER_QUEUE_JOBS)
    if support != "supported":
        return {"support": support, "jobs": []}
    rows: List[Dict[str, Any]] = []
    native_ids: set[str] = set()
    for index, job in enumerate(jobs, start=1):
        validate_deadline(deadline_at_ms)
        if not isinstance(job, dict):
            return {"support": "unknown_version", "jobs": []}
        native_id = _job_id(job)
        if native_id is None:
            # Position and display text cannot identify a replacement job.
            # Reject the entire observation rather than minting a refreshable
            # snapshot identity that could silently retarget.
            return {"support": "unknown_version", "jobs": []}
        if native_id in native_ids:
            # GetRenderJobStatus is keyed only by native job ID. Duplicate IDs
            # cannot support exact refresh correlation for either position.
            return {"support": "unknown_version", "jobs": []}
        native_ids.add(native_id)
        status_support, status = ("unavailable", None)
        status_support, status = _safe_call(project, "GetRenderJobStatus", native_id)
        if status_support == "supported" and not isinstance(status, dict):
            status_support, status = "unknown_version", None
        rows.append(
            {
                "index": index,
                "native_id": native_id,
                "job": job,
                "status_support": status_support,
                "status": status,
            }
        )
    return {"support": "supported", "jobs": rows}


def _current_page(conn: Any) -> Any:
    resolve = getattr(conn, "resolve", None)
    getter = getattr(resolve, "GetCurrentPage", None)
    return getter() if callable(getter) else None


def _identity_context(conn: Any) -> Dict[str, Any]:
    project = getattr(conn, "project", None)
    timeline = getattr(conn, "timeline", None)
    project_name = project.GetName() if callable(getattr(project, "GetName", None)) else None
    timeline_name = timeline.GetName() if callable(getattr(timeline, "GetName", None)) else None
    return {
        "project_open": project is not None,
        "project_id": documented_unique_id(project),
        "project_name": project_name,
        "timeline_id": documented_unique_id(timeline) if timeline is not None else None,
        "timeline_name": timeline_name,
        "page": _current_page(conn),
    }


def _context(
    conn: Any,
    jobs: Dict[str, Any],
    settings: Dict[str, Any],
    *,
    identity: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    structural_jobs = [
        {
            "index": row["index"],
            "native_id": row["native_id"],
            "name": row["job"].get("CustomName") or row["job"].get("OutputFilename") or row["job"].get("TimelineName"),
        }
        for row in jobs.get("jobs", [])
    ]
    return {
        **(identity if identity is not None else _identity_context(conn)),
        "queue_support": jobs.get("support"),
        "queue_structure": structural_jobs,
        "settings_support": settings.get("support"),
        "settings": settings.get("settings"),
        "format_codec": settings.get("format_codec"),
        "mode": settings.get("mode"),
    }


def inspect_sdk_render_state(conn: Any, *, deadline_at_ms: int) -> Dict[str, Any]:
    """Read all render discovery/status surfaces once and prove user-context stability."""

    validate_deadline(deadline_at_ms)
    project = getattr(conn, "project", None)
    before_jobs: Dict[str, Any]
    before_settings: Dict[str, Any]
    before_jobs = _render_jobs(project, deadline_at_ms)
    before_settings = _render_settings(project)
    before = _context(conn, before_jobs, before_settings)
    validate_deadline(deadline_at_ms)
    discovery = _render_discovery(conn, deadline_at_ms)
    presets = _render_presets(conn)
    settings = _render_settings(project)
    jobs = _render_jobs(project, deadline_at_ms)
    observed = _context(conn, jobs, settings)
    validate_deadline(deadline_at_ms)
    conn.refresh()
    after_jobs = _render_jobs(getattr(conn, "project", None), deadline_at_ms)
    after_settings = _render_settings(getattr(conn, "project", None))
    after = _context(conn, after_jobs, after_settings)
    validate_deadline(deadline_at_ms)
    # Include the exact middle settings/queue projection being returned. This
    # rejects A→B→A transitions instead of validating only the outer bracket.
    canonical = lambda value: json.dumps(value, sort_keys=True, default=str)
    context_unchanged = canonical(before) == canonical(observed) == canonical(after)
    return {
        "before": before,
        "after": after,
        "context_unchanged": context_unchanged,
        "discovery": discovery,
        "presets": presets,
        "settings": settings,
        "jobs": jobs,
    }
