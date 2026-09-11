from __future__ import annotations

import re
from difflib import get_close_matches
from typing import Any, Dict, List, Optional

from ...errors import APICallFailed, ValidationError
from .common import _get_callable


def get_render_presets(conn) -> List[str]:
    getter = _get_callable(getattr(conn, "project", None), "GetRenderPresetList")
    if getter is None:
        raise APICallFailed("GetRenderPresetList not available.")
    preset_list = getter()
    return preset_list if preset_list else []


def _render_preset_name(preset: Any) -> Optional[str]:
    if isinstance(preset, dict):
        for key in ("Name", "PresetName", "name", "preset_name"):
            value = preset.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    elif preset is not None and str(preset).strip():
        return str(preset).strip()
    return None


def save_render_preset(conn, name: str) -> None:
    """Create a new preset only when native success and exact catalog delta agree."""
    project = getattr(conn, "project", None)
    getter = _get_callable(project, "GetRenderPresetList")
    saver = _get_callable(project, "SaveAsNewRenderPreset")
    if getter is None or saver is None:
        raise APICallFailed("DaVinci Resolve render preset save or readback is unavailable.")

    def catalog():
        raw = getter()
        if not isinstance(raw, list):
            raise APICallFailed("DaVinci Resolve render preset readback is unavailable.")
        names = [_render_preset_name(value) for value in raw]
        if any(value is None for value in names) or len(set(names)) != len(names):
            raise APICallFailed("DaVinci Resolve returned an ambiguous render preset list.")
        return set(names)

    before = catalog()
    if name in before:
        raise ValidationError("Render preset already exists; choose a new name.")
    if saver(name) is not True:
        raise APICallFailed("DaVinci Resolve did not confirm the render preset save.")
    if catalog() != before | {name}:
        raise APICallFailed("DaVinci Resolve render preset save did not match readback.")


def _normalize_render_preset_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).casefold())


def _summarize_render_presets(presets: List[Any]) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    for index, preset in enumerate(presets, start=1):
        name = _render_preset_name(preset)
        summary: Dict[str, Any] = {"index": index, "name": name}
        if isinstance(preset, dict):
            summary.update({k: v for k, v in preset.items() if k not in summary})
        summaries.append(summary)
    return summaries


def _resolve_render_preset_selector(conn, selector: str) -> tuple[str, List[Any]]:
    requested_preset = str(selector).strip()
    presets = get_render_presets(conn)
    named_presets = [
        (index, preset_name)
        for index, preset in enumerate(presets, start=1)
        if (preset_name := _render_preset_name(preset))
    ]

    for _index, preset_name in named_presets:
        if preset_name == requested_preset:
            return preset_name, presets

    requested_casefold = requested_preset.casefold()
    case_matches = [preset_name for _index, preset_name in named_presets if preset_name.casefold() == requested_casefold]
    if len(case_matches) == 1:
        return case_matches[0], presets
    if len(case_matches) > 1:
        raise ValidationError(
            "Render preset selector is ambiguous.",
            details={
                "requested_preset": requested_preset,
                "matches": case_matches,
                "available_presets": _summarize_render_presets(presets),
                "hint": "Pass the exact preset name from `cutagent render presets --json`.",
            },
        )

    requested_normalized = _normalize_render_preset_name(requested_preset)
    normalized_matches = [
        preset_name
        for _index, preset_name in named_presets
        if _normalize_render_preset_name(preset_name) == requested_normalized
    ]
    if len(normalized_matches) == 1:
        return normalized_matches[0], presets
    if len(normalized_matches) > 1:
        raise ValidationError(
            "Render preset selector is ambiguous.",
            details={
                "requested_preset": requested_preset,
                "matches": normalized_matches,
                "available_presets": _summarize_render_presets(presets),
                "hint": "Pass the exact preset name from `cutagent render presets --json`.",
            },
        )

    if requested_preset.isdecimal():
        preset_index = int(requested_preset)
        if preset_index > 0 and preset_index <= len(named_presets):
            return named_presets[preset_index - 1][1], presets

    partial_matches = [
        preset_name
        for _index, preset_name in named_presets
        if requested_normalized and requested_normalized in _normalize_render_preset_name(preset_name)
    ]
    if len(partial_matches) == 1:
        return partial_matches[0], presets
    if len(partial_matches) > 1:
        raise ValidationError(
            "Render preset selector is ambiguous.",
            details={
                "requested_preset": requested_preset,
                "matches": partial_matches,
                "available_presets": _summarize_render_presets(presets),
                "hint": "Multiple render presets match this selector; pass an exact preset name or 1-based index.",
            },
        )

    preset_names = [preset_name for _index, preset_name in named_presets]
    raise ValidationError(
        "Render preset not found.",
        details={
            "requested_preset": requested_preset,
            "available_presets": _summarize_render_presets(presets),
            "suggestions": get_close_matches(requested_preset, preset_names, n=5, cutoff=0.45),
            "hint": "Run `cutagent render presets --json` and pass the exact preset name or a 1-based preset index.",
        },
    )


def get_render_formats(conn) -> Dict[str, str]:
    getter = _get_callable(getattr(conn, "project", None), "GetRenderFormats")
    if getter is None:
        raise APICallFailed("GetRenderFormats not available.")
    fmt_dict = getter()
    return fmt_dict if isinstance(fmt_dict, dict) else {}


def get_audio_render_formats(conn) -> Dict[str, str]:
    """Return the dedicated audio-only render format inventory added in DaVinci Resolve 21.1."""
    getter = _get_callable(getattr(conn, "project", None), "GetAudioRenderFormats")
    if getter is None:
        raise APICallFailed("GetAudioRenderFormats not available.")
    fmt_dict = getter()
    return fmt_dict if isinstance(fmt_dict, dict) else {}


def get_render_codecs(conn, format_name: str) -> Dict[str, str]:
    getter = _get_callable(getattr(conn, "project", None), "GetRenderCodecs")
    if getter is None:
        raise APICallFailed("GetRenderCodecs not available.")
    resolved_format, available_formats = _resolve_render_format_selector(conn, format_name)
    candidate_formats = [resolved_format]
    extension = available_formats.get(resolved_format) if available_formats else None
    if extension is not None and str(extension) not in candidate_formats:
        candidate_formats.append(str(extension))

    for candidate_format in candidate_formats:
        codec_dict = getter(candidate_format)
        if isinstance(codec_dict, dict) and codec_dict:
            return codec_dict
    return {}


def get_audio_render_codecs(conn, format_name: str) -> Dict[str, str]:
    """Return audio codecs for one exact audio render format."""
    getter = _get_callable(getattr(conn, "project", None), "GetAudioRenderCodecs")
    if getter is None:
        raise APICallFailed("GetAudioRenderCodecs not available.")
    formats = get_audio_render_formats(conn)
    requested = str(format_name or "").strip()
    if not requested:
        raise ValidationError("Audio render format must not be empty.")
    matches = [
        (label, extension)
        for label, extension in formats.items()
        if requested.casefold() in {str(label).casefold(), str(extension).casefold()}
    ]
    if len(matches) != 1:
        raise ValidationError(
            "Audio render format not found." if not matches else "Audio render format is ambiguous.",
            details={"requested_format": requested, "available_formats": sorted(str(label) for label in formats)},
        )
    label, extension = matches[0]
    candidates = [extension, label]
    for candidate in candidates:
        codec_dict = getter(str(candidate))
        if isinstance(codec_dict, dict) and codec_dict:
            return codec_dict
    return {}


def get_render_resolutions(
    conn,
    format_name: Optional[str] = None,
    codec_name: Optional[str] = None,
) -> List[Any]:
    getter = _get_callable(getattr(conn, "project", None), "GetRenderResolutions")
    if getter is None:
        raise APICallFailed("GetRenderResolutions not available.")

    if not format_name:
        resolutions = getter()
        return resolutions if isinstance(resolutions, list) else []

    resolved_format, available_formats = _resolve_render_format_selector(conn, format_name)
    candidate_formats = [resolved_format]
    extension = available_formats.get(resolved_format) if available_formats else None
    if extension is not None and str(extension) not in candidate_formats:
        candidate_formats.append(str(extension))

    if codec_name:
        resolved_codec, _available_codecs = _resolve_render_codec_selector(
            conn,
            format_name=resolved_format,
            codec_name=codec_name,
        )
        for candidate_format in candidate_formats:
            resolutions = getter(candidate_format, resolved_codec)
            if isinstance(resolutions, list) and resolutions:
                return resolutions
        return []

    for candidate_format in candidate_formats:
        resolutions = getter(candidate_format)
        if isinstance(resolutions, list) and resolutions:
            return resolutions

    codec_dict = get_render_codecs(conn, resolved_format)
    for codec_value in codec_dict.values():
        for candidate_format in candidate_formats:
            resolutions = getter(candidate_format, str(codec_value))
            if isinstance(resolutions, list) and resolutions:
                return resolutions
    return []


def _resolve_render_format_selector(conn, format_name: str) -> tuple[str, Dict[str, str]]:
    requested_format = str(format_name)
    try:
        available_formats = get_render_formats(conn)
    except APICallFailed:
        available_formats = {}

    if not available_formats:
        return requested_format, available_formats

    for candidate in available_formats.keys():
        if str(candidate) == requested_format:
            return str(candidate), available_formats

    requested_casefold = requested_format.casefold()
    for candidate in available_formats.keys():
        if str(candidate).casefold() == requested_casefold:
            return str(candidate), available_formats

    requested_normalized = _normalize_render_preset_name(requested_format)
    for candidate in available_formats.keys():
        if _normalize_render_preset_name(str(candidate)) == requested_normalized:
            return str(candidate), available_formats

    for candidate, extension in available_formats.items():
        if str(extension).casefold().lstrip(".") == requested_casefold.lstrip("."):
            return str(candidate), available_formats

    raise ValidationError(
        "Render format not available.",
        details={
            "requested_format": requested_format,
            "available_formats": available_formats,
            "hint": "Run `cutagent render formats --json` and pass one of the DaVinci Resolve format names.",
        },
    )


def _resolve_render_codec_selector(
    conn,
    *,
    format_name: str,
    codec_name: Optional[str],
) -> tuple[str, Dict[str, str] | None]:
    requested_codec = "" if codec_name is None else str(codec_name)
    try:
        available_codecs = get_render_codecs(conn, format_name)
    except APICallFailed:
        available_codecs = None

    if available_codecs is None:
        return requested_codec, available_codecs
    if not available_codecs:
        return "", available_codecs
    if not requested_codec:
        return "", available_codecs

    codec_items = [(str(description), str(codec_value)) for description, codec_value in available_codecs.items()]

    for description, codec_value in codec_items:
        if requested_codec in (description, codec_value):
            return codec_value, available_codecs

    requested_casefold = requested_codec.casefold()
    for description, codec_value in codec_items:
        if requested_casefold in (description.casefold(), codec_value.casefold()):
            return codec_value, available_codecs

    requested_normalized = _normalize_render_preset_name(requested_codec)
    for description, codec_value in codec_items:
        if requested_normalized in (
            _normalize_render_preset_name(description),
            _normalize_render_preset_name(codec_value),
        ):
            return codec_value, available_codecs

    raise ValidationError(
        "Render codec not available for format.",
        details={
            "requested_format": format_name,
            "requested_codec": requested_codec,
            "available_codecs": available_codecs,
            "hint": "Run `cutagent render codecs FORMAT --json` and pass one of the DaVinci Resolve codec names or labels.",
        },
    )


def _set_render_format_and_codec(
    conn,
    *,
    format_name: str,
    codec_name: Optional[str] = None,
) -> tuple[str, str]:
    set_format_and_codec = _get_callable(getattr(conn, "project", None), "SetCurrentRenderFormatAndCodec")
    if set_format_and_codec is None:
        raise APICallFailed("SetCurrentRenderFormatAndCodec not available.")

    resolved_format, available_formats = _resolve_render_format_selector(conn, format_name)
    resolved_codec, available_codecs = _resolve_render_codec_selector(
        conn,
        format_name=resolved_format,
        codec_name=codec_name,
    )

    setter_format = str(available_formats.get(resolved_format) or resolved_format)
    result = set_format_and_codec(setter_format, resolved_codec)
    if result is False:
        raise APICallFailed(
            "Failed to apply render format and codec.",
            details={
                "requested_format": format_name,
                "requested_codec": codec_name,
                "resolved_format": resolved_format,
                "setter_format": setter_format,
                "resolved_codec": resolved_codec,
                "available_formats": available_formats,
                "available_codecs": available_codecs,
            },
        )
    return setter_format, resolved_codec


def load_render_preset(conn, name: str) -> Dict[str, Any]:
    resolved_name, presets = _resolve_render_preset_selector(conn, name)
    loader = _get_callable(getattr(conn, "project", None), "LoadRenderPreset")
    if loader is None:
        raise APICallFailed("LoadRenderPreset not available.")
    result = loader(resolved_name)
    if result:
        return {
            "loaded": True,
            "preset": resolved_name,
            "requested_preset": str(name),
        }
    raise APICallFailed(
        "DaVinci Resolve rejected render preset load.",
        details={
            "requested_preset": str(name),
            "resolved_preset": resolved_name,
            "available_presets": _summarize_render_presets(presets),
        },
    )


def _render_preset_name_exists(conn, preset_name: str) -> tuple[bool, List[Any]]:
    try:
        presets = get_render_presets(conn)
    except Exception:
        return False, []

    normalized_preset_name = _normalize_render_preset_name(preset_name)
    for preset in presets:
        existing_name = _render_preset_name(preset)
        if existing_name and _normalize_render_preset_name(existing_name) == normalized_preset_name:
            return True, presets
    return False, presets
