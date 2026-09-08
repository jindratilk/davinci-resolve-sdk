from __future__ import annotations

import os
from difflib import get_close_matches
from typing import Any, Dict, Optional

from ...errors import APICallFailed, ValidationError
from .common import _sleep
from .presets import _normalize_render_preset_name, _render_preset_name


def get_quick_export_presets(conn) -> list:
    if not conn.project:
        raise APICallFailed("No active project.")
    getter = getattr(conn.project, "GetQuickExportRenderPresets", None)
    if not getter:
        raise APICallFailed("GetQuickExportRenderPresets not available (requires DaVinci Resolve 20+).")
    presets = getter()
    return presets if presets else []


def _quick_export_preset_name(preset: Any) -> Optional[str]:
    return _render_preset_name(preset)


def _summarize_quick_export_presets(presets: list[Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, preset in enumerate(presets, start=1):
        name = _quick_export_preset_name(preset)
        summary: dict[str, Any] = {"index": index, "name": name}
        if isinstance(preset, dict):
            summary.update({k: v for k, v in preset.items() if k not in summary})
        summaries.append(summary)
    return summaries


def _resolve_quick_export_preset_selector(conn, selector: str) -> tuple[str, list[Any]]:
    requested_preset = str(selector).strip()
    presets = get_quick_export_presets(conn)
    named_presets = [
        (index, preset_name)
        for index, preset in enumerate(presets, start=1)
        if (preset_name := _quick_export_preset_name(preset))
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
            "Quick export preset selector is ambiguous.",
            details={
                "requested_preset": requested_preset,
                "matches": case_matches,
                "available_presets": _summarize_quick_export_presets(presets),
                "hint": "Pass the exact quick export preset name from `cutagent render quick-export-presets --json`.",
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
            "Quick export preset selector is ambiguous.",
            details={
                "requested_preset": requested_preset,
                "matches": normalized_matches,
                "available_presets": _summarize_quick_export_presets(presets),
                "hint": "Pass the exact quick export preset name from `cutagent render quick-export-presets --json`.",
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
            "Quick export preset selector is ambiguous.",
            details={
                "requested_preset": requested_preset,
                "matches": partial_matches,
                "available_presets": _summarize_quick_export_presets(presets),
                "hint": "Multiple quick export presets match this selector; pass an exact preset name or 1-based index.",
            },
        )

    preset_names = [preset_name for _index, preset_name in named_presets]
    raise ValidationError(
        "Quick export preset not found.",
        details={
            "requested_preset": requested_preset,
            "available_presets": _summarize_quick_export_presets(presets),
            "suggestions": get_close_matches(requested_preset, preset_names, n=5, cutoff=0.45),
            "hint": "Run `cutagent render quick-export-presets --json` and pass the exact preset name or a 1-based preset index.",
        },
    )


def _resolve_quick_export_output_path(
    target_dir: str,
    *,
    known_entries: set[str],
    settle_attempts: int = 20,
    settle_delay_s: float = 0.25,
) -> str | None:
    base_dir = os.path.abspath(target_dir)
    os.makedirs(base_dir, exist_ok=True)
    attempts = max(int(settle_attempts), 1)
    for attempt in range(1, attempts + 1):
        try:
            current_entries = {
                entry
                for entry in os.listdir(base_dir)
                if os.path.isfile(os.path.join(base_dir, entry))
            }
        except OSError:
            current_entries = set()
        new_entries = sorted(current_entries - known_entries)
        if new_entries:
            return os.path.join(base_dir, new_entries[-1])
        if attempt < attempts:
            _sleep(settle_delay_s)
    return None


def render_with_quick_export(
    conn,
    preset: str,
    *,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    if not conn.project:
        raise APICallFailed("No active project.")
    resolved_preset, available_presets = _resolve_quick_export_preset_selector(conn, preset)
    renderer = getattr(conn.project, "RenderWithQuickExport", None)
    if not renderer:
        raise APICallFailed("RenderWithQuickExport not available (requires DaVinci Resolve 20+).")

    params: Dict[str, Any] = {}
    known_entries: set[str] = set()
    if output_path:
        target_dir = os.path.abspath(output_path)
        os.makedirs(target_dir, exist_ok=True)
        params["TargetDir"] = target_dir
        try:
            known_entries = {
                entry
                for entry in os.listdir(target_dir)
                if os.path.isfile(os.path.join(target_dir, entry))
            }
        except OSError:
            known_entries = set()

    result = renderer(resolved_preset, params) if params else renderer(resolved_preset)
    if isinstance(result, str):
        raise APICallFailed(
            "Quick export failed.",
            details={
                "requested_preset": preset,
                "resolved_preset": resolved_preset,
                "api_result": result,
                "available_presets": _summarize_quick_export_presets(available_presets),
            },
        )
    if isinstance(result, dict):
        status_text = str(result.get("Status") or result.get("status") or result.get("JobStatus") or "").casefold()
        if status_text and any(token in status_text for token in ("fail", "error", "not attempted", "cancel")):
            raise APICallFailed(
                "Quick export failed.",
                details={
                    "requested_preset": preset,
                    "resolved_preset": resolved_preset,
                    "api_result": result,
                    "available_presets": _summarize_quick_export_presets(available_presets),
                },
            )
    if result:
        data: Dict[str, Any] = {
            "success": True,
            "preset": resolved_preset,
            "requested_preset": str(preset),
            "output_path": output_path,
        }
        if output_path:
            resolved_output = _resolve_quick_export_output_path(params["TargetDir"], known_entries=known_entries)
            if not resolved_output:
                raise APICallFailed(
                    "Quick export completed but no output file was created in the target directory.",
                    details={
                        "requested_preset": preset,
                        "resolved_preset": resolved_preset,
                        "target_dir": params["TargetDir"],
                    },
                )
            data["output_path"] = resolved_output
        return data
    raise APICallFailed(
        "Quick export failed.",
        details={
            "requested_preset": preset,
            "resolved_preset": resolved_preset,
            "api_result": result,
            "available_presets": _summarize_quick_export_presets(available_presets),
        },
    )
