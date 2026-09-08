from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ...errors import APICallFailed, CapabilityNegotiationFailed, ValidationError
from .common import _get_callable
from .presets import (
    _normalize_render_preset_name,
    _render_preset_name_exists,
    _resolve_render_preset_selector,
    _summarize_render_presets,
)

__all__ = [
    "_prepare_render_preset_export_path",
    "_resolve_render_preset_import_path",
    "export_burnin_preset",
    "export_render_preset",
    "import_burnin_preset",
    "import_render_preset",
    "_normalize_render_preset_name",
    "_render_preset_name_exists",
    "_resolve_render_preset_selector",
    "_summarize_render_presets",
]


def _resolve_render_preset_import_path(path: str) -> Path:
    input_path = Path(path).expanduser()
    if not input_path.exists():
        raise ValidationError(
            "Render preset path not found.",
            details={"path": path},
        )

    resolved_path = input_path
    if input_path.is_dir():
        xml_files = sorted(candidate for candidate in input_path.rglob("*.xml") if candidate.is_file())
        if not xml_files:
            raise ValidationError(
                "Render preset bundle does not contain an XML preset file.",
                details={"path": path},
            )
        if len(xml_files) > 1:
            raise ValidationError(
                "Render preset bundle contains multiple XML files; import the intended XML path explicitly.",
                details={
                    "path": path,
                    "xml_files": [str(candidate) for candidate in xml_files],
                },
            )
        resolved_path = xml_files[0]
    elif not input_path.is_file():
        raise ValidationError(
            "Render preset path is not a file or bundle directory.",
            details={"path": path, "resolved_path": str(input_path)},
        )
    elif input_path.suffix.casefold() != ".xml":
        raise ValidationError(
            "Render preset import requires an XML preset file or `.drpx` bundle directory.",
            details={
                "path": path,
                "resolved_path": str(input_path),
                "hint": "DaVinci Resolve exports `.drpx` render presets as directories containing XML. Pass the bundle directory or the XML file inside it.",
            },
        )
    return resolved_path


def import_render_preset(conn, path: str) -> Dict[str, Any]:
    resolved_path = _resolve_render_preset_import_path(path)
    preset_name = resolved_path.stem
    already_exists, existing_presets = _render_preset_name_exists(conn, preset_name)
    if already_exists:
        return {
            "imported": False,
            "already_exists": True,
            "preset_name": preset_name,
            "path": path,
            "resolved_path": str(resolved_path),
            "available_presets": _summarize_render_presets(existing_presets),
            "hint": (
                "A render preset with this name already exists. Rename the XML file inside the "
                "`.drpx` bundle before importing a modified preset variant, or use `render preset-load` "
                "to load the existing preset."
            ),
        }

    importer = _get_callable(getattr(conn, "resolve", None), "ImportRenderPreset")
    if importer is None:
        raise APICallFailed("ImportRenderPreset not available.")

    result = importer(str(resolved_path))
    payload = {
        "imported": bool(result),
        "already_exists": False,
        "preset_name": preset_name,
        "path": path,
        "resolved_path": str(resolved_path),
    }
    if result:
        return payload

    raise APICallFailed(
        "Render preset import failed.",
        details={
            "path": path,
            "resolved_path": str(resolved_path),
            "preset_name": preset_name,
            "available_presets": _summarize_render_presets(existing_presets),
            "hint": "Verify that the XML was exported by DaVinci Resolve as a render preset, not a burn-in or unrelated preset file.",
        },
    )


def _prepare_render_preset_export_path(path: str) -> Path:
    output_path = Path(path).expanduser()
    if output_path.exists() and not output_path.is_dir():
        raise ValidationError(
            "Render preset export path already exists and is not a bundle directory.",
            details={
                "path": path,
                "resolved_path": str(output_path),
                "hint": "Pass a new `.drpx` bundle directory path or remove the existing file first.",
            },
        )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValidationError(
            "Render preset export parent directory is not writable.",
            details={
                "path": path,
                "parent": str(output_path.parent),
                "error": str(exc),
            },
        ) from exc
    return output_path


def export_render_preset(conn, name: str, path: str) -> Dict[str, Any]:
    resolved_name, presets = _resolve_render_preset_selector(conn, name)
    output_path = _prepare_render_preset_export_path(path)
    exporter = _get_callable(getattr(conn, "resolve", None), "ExportRenderPreset")
    if exporter is None:
        raise APICallFailed("ExportRenderPreset not available.")
    result = exporter(resolved_name, str(output_path))
    if result:
        return {
            "exported": True,
            "name": resolved_name,
            "requested_name": str(name),
            "path": path,
            "resolved_path": str(output_path),
            "exists": output_path.exists(),
        }
    raise CapabilityNegotiationFailed(
        "Render preset is listed but this DaVinci Resolve runtime refused to export it.",
        details={
            "requested_name": str(name),
            "resolved_name": resolved_name,
            "path": path,
            "resolved_path": str(output_path),
            "available_presets": _summarize_render_presets(presets),
            "hint": "DaVinci Resolve may refuse to export built-in presets. Use `render preset-save` to create a custom preset, then export that custom preset.",
        },
    )


def import_burnin_preset(conn, path: str) -> Dict[str, Any]:
    importer = _get_callable(getattr(conn, "resolve", None), "ImportBurnInPreset")
    if importer is None:
        raise APICallFailed("ImportBurnInPreset not available.")
    result = importer(path)
    return {"imported": bool(result), "path": path}


def export_burnin_preset(conn, name: str, path: str) -> Dict[str, Any]:
    exporter = _get_callable(getattr(conn, "resolve", None), "ExportBurnInPreset")
    if exporter is None:
        raise APICallFailed("ExportBurnInPreset not available.")
    result = exporter(name, path)
    return {"exported": bool(result), "name": name, "path": path}
