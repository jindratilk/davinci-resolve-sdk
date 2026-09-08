"""Color grading commands."""

from __future__ import annotations

import os
import json
import math
import colorsys
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import typer

from ..confirmation import require_force_for_machine_mode
from ..capabilities import get_capabilities
from ..connection import get_connection
from ..errors import handle_errors, APICallFailed, CapabilityNegotiationFailed, CLIError, ColorRenderProofFailed, ClipNotFound, ValidationError
from ..external_tools import resolve_tool
from ..output import output, success, is_dry_run, dry_run_message, set_capability_context, set_execution_engine, set_recoverability, set_verification_status
from ..policy import enforce_mutation_policy
from ..core import color_ops
from ..core import color_source_grade
from ..core import color_page_db
from ..core import clip_ops
from ..core import gallery_ops
from ..core import fx_template_ops
from ..core import mutation_target
from ..core import lut_generator
from ..core import timeline_ops

app = typer.Typer(help="Color grading operations.")

wheels_app = typer.Typer(help="Color wheels emulation (CDL/LUT).")
app.add_typer(wheels_app, name="wheels")
primary_app = typer.Typer(help="Primary grading via clip-attached Fusion color tools.")
app.add_typer(primary_app, name="primary")
graph_app = typer.Typer(help="Fusion grading graph validation and normalization.")
app.add_typer(graph_app, name="graph")
comp_app = typer.Typer(help="Fusion grading comp recovery operations.")
app.add_typer(comp_app, name="comp")
window_app = typer.Typer(help="Window/mask grading helpers via clip-attached Fusion tools.")
app.add_typer(window_app, name="window")
qualifier_app = typer.Typer(help="Qualifier helpers via clip-attached Fusion keyers.")
app.add_typer(qualifier_app, name="qualifier")
tracker_app = typer.Typer(help="Tracking helpers via clip-attached Fusion tracker tools.")
app.add_typer(tracker_app, name="tracker")
mask_app = typer.Typer(help="Mask stack inspection and orchestration.")
app.add_typer(mask_app, name="mask")
secondary_app = typer.Typer(help="Higher-level secondary grading helpers.")
app.add_typer(secondary_app, name="secondary")
fx_app = typer.Typer(help="Fusion-template grading effects without GUI automation.")
app.add_typer(fx_app, name="fx")
page_app = typer.Typer(help="DB-backed native Color page operations (Lift/Gamma/Gain/Offset, Saturation).")
app.add_typer(page_app, name="page")


def _node_stack_layer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 1


def _node_stack_call(function, *args, node_stack_layer_index: int):
    return (
        function(*args)
        if node_stack_layer_index == 1
        else function(*args, node_stack_layer_index=node_stack_layer_index)
    )


def _validate_auto_color_request(input_file: str, node: int, frame: int, apply: bool, clip_name: Optional[str]) -> Path:
    if node < 1:
        raise ValidationError(
            "--node must be a positive integer.",
            details={"node": node, "minimum": 1},
            recoverability="not_applicable",
        )
    if frame < 0:
        raise ValidationError(
            "--frame must be a non-negative integer.",
            details={"frame": frame, "minimum": 0},
            recoverability="not_applicable",
        )
    path = Path(input_file).expanduser()
    if not path.is_file():
        raise ValidationError(
            "Input video file not found.",
            details={"input": str(path)},
            recoverability="not_applicable",
        )
    if apply and (clip_name is None or not str(clip_name).strip()):
        raise ValidationError(
            "--apply requires an explicit clip target. Use --no-apply for analysis only.",
            details={"clip_name": clip_name, "option": "--apply"},
            recoverability="not_applicable",
        )
    return path


def _resolve_output_file_path(output_path: str, *, option_name: str = "--output") -> Path:
    raw = str(output_path).strip()
    if not raw:
        raise ValidationError(
            f"{option_name} must not be empty.",
            details={"output_path": output_path},
            recoverability="not_applicable",
        )
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve(strict=False)
    if path.exists() and path.is_dir():
        raise ValidationError(
            "Output path must be a file path, not a directory.",
            details={"output_path": str(path)},
            recoverability="not_applicable",
        )
    if not path.parent.is_dir():
        raise ValidationError(
            "Output directory does not exist.",
            details={"output_path": str(path), "parent": str(path.parent)},
            recoverability="not_applicable",
        )
    return path


def _image_file_metadata(path: Path) -> dict:
    size = path.stat().st_size
    metadata = {
        "exists": path.is_file(),
        "bytes": size,
        "format": None,
        "width": None,
        "height": None,
    }
    with path.open("rb") as fh:
        header = fh.read(32)
    if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
        metadata.update(
            {
                "format": "png",
                "width": int.from_bytes(header[16:20], "big"),
                "height": int.from_bytes(header[20:24], "big"),
            }
        )
    elif header.startswith(b"\xff\xd8"):
        metadata["format"] = "jpeg"
    return metadata


def _workspace_relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _export_color_page_frame_as_still(conn, *, resolved_path: Path, requested_output_path: str) -> dict:
    attempts: list[dict[str, object]] = []
    for attempt in range(1, 5):
        try:
            with color_ops._with_required_page(conn, "color"):
                ok = conn.project.ExportCurrentFrameAsStill(str(resolved_path))
        except APICallFailed:
            raise
        except Exception as exc:
            attempts.append({"attempt": attempt, "error": str(exc)})
            ok = False
        if ok and resolved_path.is_file():
            return _image_file_metadata(resolved_path)
        attempts.append(
            {
                "attempt": attempt,
                "api_result": ok,
                "file_created": resolved_path.is_file(),
            }
        )
        if attempt < 4:
            time.sleep(0.75 * attempt)

    raise APICallFailed(
        "Failed to export current Color Page frame.",
        details={
            "output_path": str(resolved_path),
            "requested_output_path": requested_output_path,
            "api_call": "Project.ExportCurrentFrameAsStill",
            "api_result": attempts[-1].get("api_result"),
            "required_page": "color",
            "attempts": attempts,
        },
    )


def _run_frame_probe(path: Path) -> tuple[int, int]:
    cmd = [
        resolve_tool("ffprobe"),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise APICallFailed(
            "Failed to inspect exported frame dimensions.",
            details={"output_path": str(path), "stderr": result.stderr[-500:], "tool": "ffprobe"},
        )
    try:
        payload = json.loads(result.stdout or "{}")
        stream = (payload.get("streams") or [{}])[0]
        width = int(stream["width"])
        height = int(stream["height"])
    except Exception as exc:
        raise APICallFailed(
            "Exported frame dimension probe returned invalid data.",
            details={"output_path": str(path), "stdout": result.stdout[-500:], "tool": "ffprobe"},
        ) from exc
    if width <= 0 or height <= 0:
        raise APICallFailed(
            "Exported frame dimensions must be positive.",
            details={"output_path": str(path), "width": width, "height": height},
        )
    return width, height


def _load_frame_rgb_array(path: Path):
    import numpy as np

    width, height = _run_frame_probe(path)
    cmd = [
        resolve_tool("ffmpeg"),
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode != 0:
        raise APICallFailed(
            "Failed to decode exported frame for scope analysis.",
            details={"output_path": str(path), "stderr": result.stderr.decode("utf-8", errors="replace")[-500:], "tool": "ffmpeg"},
        )
    expected_bytes = width * height * 3
    if len(result.stdout) != expected_bytes:
        raise APICallFailed(
            "Decoded frame byte count did not match probed dimensions.",
            details={
                "output_path": str(path),
                "width": width,
                "height": height,
                "expected_bytes": expected_bytes,
                "actual_bytes": len(result.stdout),
            },
        )
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape((height, width, 3))


def _rounded_percentiles(values, percentiles: tuple[int, ...] = (0, 1, 5, 50, 95, 99, 100)) -> dict[str, float]:
    import numpy as np

    computed = np.percentile(values, percentiles)
    return {f"p{pct}": round(float(value), 3) for pct, value in zip(percentiles, computed)}


def _scope_channel_stats(values) -> dict[str, object]:
    import numpy as np

    return {
        "min": round(float(np.min(values)), 3),
        "max": round(float(np.max(values)), 3),
        "avg": round(float(np.mean(values)), 3),
        "percentiles": _rounded_percentiles(values),
    }


def _video_level_ire(value: float) -> float:
    return round(((float(value) - 16.0) / 219.0) * 100.0, 3)


def _analyze_scope_pixels(rgb) -> dict[str, object]:
    import numpy as np

    rgb_float = rgb.astype(np.float32)
    red = rgb_float[:, :, 0]
    green = rgb_float[:, :, 1]
    blue = rgb_float[:, :, 2]
    luma = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
    luma_stats = _scope_channel_stats(luma)
    luma_percentiles_ire = {
        key: _video_level_ire(value)
        for key, value in luma_stats["percentiles"].items()
    }

    rgb_norm = rgb_float / 255.0
    red_n = rgb_norm[:, :, 0]
    green_n = rgb_norm[:, :, 1]
    blue_n = rgb_norm[:, :, 2]
    y_norm = (0.2126 * red_n) + (0.7152 * green_n) + (0.0722 * blue_n)
    cb = (blue_n - y_norm) / (2.0 * (1.0 - 0.0722))
    cr = (red_n - y_norm) / (2.0 * (1.0 - 0.2126))
    chroma = np.sqrt((cb * cb) + (cr * cr))
    avg_cb = round(float(np.mean(cb)), 5)
    avg_cr = round(float(np.mean(cr)), 5)
    avg_hue = round(float((math.degrees(math.atan2(avg_cr, avg_cb)) + 360.0) % 360.0), 3)
    skin_line_angle = 123.0
    skin_delta = abs(((avg_hue - skin_line_angle + 180.0) % 360.0) - 180.0)

    return {
        "frame": {"width": int(rgb.shape[1]), "height": int(rgb.shape[0]), "pixel_count": int(rgb.shape[0] * rgb.shape[1])},
        "waveform": {
            "luma_code_value": luma_stats,
            "luma_video_level_ire": {
                "min": _video_level_ire(luma_stats["min"]),
                "max": _video_level_ire(luma_stats["max"]),
                "avg": _video_level_ire(luma_stats["avg"]),
                "percentiles": luma_percentiles_ire,
            },
            "shadow_clip_percent": round(float(np.mean(luma <= 5.0) * 100.0), 4),
            "highlight_clip_percent": round(float(np.mean(luma >= 250.0) * 100.0), 4),
        },
        "rgb_parade": {
            "red": _scope_channel_stats(red),
            "green": _scope_channel_stats(green),
            "blue": _scope_channel_stats(blue),
        },
        "vectorscope": {
            "avg_cb": avg_cb,
            "avg_cr": avg_cr,
            "avg_hue_degrees": avg_hue,
            "max_chroma": round(float(np.max(chroma)), 5),
            "p95_chroma": round(float(np.percentile(chroma, 95)), 5),
            "skin_line_reference_degrees": skin_line_angle,
            "avg_hue_to_skin_line_delta_degrees": round(float(skin_delta), 3),
        },
    }


FALSE_COLOR_BANDS: tuple[dict[str, object], ...] = (
    {"id": "crushed_black", "label": "Crushed black", "min_ire": None, "max_ire": 0.0, "false_color": "purple"},
    {"id": "deep_shadow", "label": "Deep shadow", "min_ire": 0.0, "max_ire": 20.0, "false_color": "blue"},
    {"id": "shadow", "label": "Shadow", "min_ire": 20.0, "max_ire": 40.0, "false_color": "cyan"},
    {"id": "skin_proper", "label": "Skin/proper exposure", "min_ire": 40.0, "max_ire": 70.0, "false_color": "green/gray/salmon"},
    {"id": "bright", "label": "Bright exposure", "min_ire": 70.0, "max_ire": 90.0, "false_color": "yellow"},
    {"id": "near_clip", "label": "Near clip", "min_ire": 90.0, "max_ire": 100.0, "false_color": "orange"},
    {"id": "clipped_white", "label": "Clipped white", "min_ire": 100.0, "max_ire": None, "false_color": "red"},
)


def _analyze_false_color_pixels(rgb) -> dict[str, object]:
    import numpy as np

    rgb_float = rgb.astype(np.float32)
    red = rgb_float[:, :, 0]
    green = rgb_float[:, :, 1]
    blue = rgb_float[:, :, 2]
    luma = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
    ire = ((luma - 16.0) / 219.0) * 100.0
    pixel_count = int(rgb.shape[0] * rgb.shape[1])
    bands: list[dict[str, object]] = []
    for band in FALSE_COLOR_BANDS:
        min_ire = band["min_ire"]
        max_ire = band["max_ire"]
        mask = np.ones_like(ire, dtype=bool)
        if min_ire is not None:
            mask &= ire >= float(min_ire)
        if max_ire is not None:
            mask &= ire < float(max_ire)
        count = int(np.count_nonzero(mask))
        bands.append(
            {
                "id": band["id"],
                "label": band["label"],
                "false_color": band["false_color"],
                "min_ire": min_ire,
                "max_ire": max_ire,
                "pixel_count": count,
                "percent": round((count / pixel_count) * 100.0, 4) if pixel_count else 0.0,
            }
        )

    dominant = max(bands, key=lambda item: int(item["pixel_count"])) if bands else None
    proper = next((band for band in bands if band["id"] == "skin_proper"), None)
    shadow_risk = sum(float(band["percent"]) for band in bands if band["id"] in {"crushed_black", "deep_shadow"})
    highlight_risk = sum(float(band["percent"]) for band in bands if band["id"] in {"near_clip", "clipped_white"})
    return {
        "frame": {"width": int(rgb.shape[1]), "height": int(rgb.shape[0]), "pixel_count": pixel_count},
        "profile": "ire_luma_tutorial",
        "luma_video_level_ire": {
            "min": round(float(np.min(ire)), 3),
            "max": round(float(np.max(ire)), 3),
            "avg": round(float(np.mean(ire)), 3),
            "percentiles": _rounded_percentiles(ire),
        },
        "bands": bands,
        "dominant_band": dominant,
        "skin_proper_exposure_percent": float(proper["percent"]) if proper else 0.0,
        "shadow_risk_percent": round(float(shadow_risk), 4),
        "highlight_risk_percent": round(float(highlight_risk), 4),
        "warnings": {
            "shadow_crush": shadow_risk >= 15.0,
            "highlight_clip": highlight_risk >= 5.0,
        },
    }


def _frame_match_region(rgb, *, x: float | None = None, y: float | None = None, radius: int = 12):
    if x is None or y is None:
        return rgb.astype("float32"), {"mode": "full_frame", "pixel_count": int(rgb.shape[0] * rgb.shape[1])}

    sample = _sample_qualifier_pixels(rgb, x=x, y=y, radius=radius)
    bounds = sample["sample"]["bounds"]
    region = rgb[
        int(bounds["top"]) : int(bounds["bottom"]) + 1,
        int(bounds["left"]) : int(bounds["right"]) + 1,
        :,
    ].astype("float32")
    return region, {
        "mode": "anchor",
        "x": round(float(x), 6),
        "y": round(float(y), 6),
        "radius": int(radius),
        "bounds": bounds,
        "pixel_count": int(region.shape[0] * region.shape[1]),
    }


def _shot_match_region_metrics(region) -> dict[str, object]:
    import numpy as np

    flat = region.reshape((-1, 3))
    avg_rgb = np.mean(flat, axis=0)
    luma = (0.2126 * flat[:, 0]) + (0.7152 * flat[:, 1]) + (0.0722 * flat[:, 2])
    luma_stats = _scope_channel_stats(luma)
    avg_sum = float(np.sum(avg_rgb))
    rgb_balance = {
        "red": round(float(avg_rgb[0] / avg_sum), 6) if avg_sum else 0.0,
        "green": round(float(avg_rgb[1] / avg_sum), 6) if avg_sum else 0.0,
        "blue": round(float(avg_rgb[2] / avg_sum), 6) if avg_sum else 0.0,
    }
    return {
        "rgb_avg": {
            "red": round(float(avg_rgb[0]), 3),
            "green": round(float(avg_rgb[1]), 3),
            "blue": round(float(avg_rgb[2]), 3),
        },
        "rgb_balance": rgb_balance,
        "luma_code_value": luma_stats,
        "luma_video_level_ire": {
            "avg": _video_level_ire(luma_stats["avg"]),
            "p50": _video_level_ire(luma_stats["percentiles"]["p50"]),
            "p95": _video_level_ire(luma_stats["percentiles"]["p95"]),
        },
    }


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _analyze_shot_match_pixels(
    reference_rgb,
    target_rgb,
    *,
    anchor_x: float | None = None,
    anchor_y: float | None = None,
    radius: int = 12,
    strength: float = 1.0,
) -> dict[str, object]:
    import numpy as np

    reference_region, region = _frame_match_region(reference_rgb, x=anchor_x, y=anchor_y, radius=radius)
    target_region, _ = _frame_match_region(target_rgb, x=anchor_x, y=anchor_y, radius=radius)
    reference = _shot_match_region_metrics(reference_region)
    target = _shot_match_region_metrics(target_region)
    ref_avg = np.array([reference["rgb_avg"]["red"], reference["rgb_avg"]["green"], reference["rgb_avg"]["blue"]], dtype=np.float32)
    tgt_avg = np.array([target["rgb_avg"]["red"], target["rgb_avg"]["green"], target["rgb_avg"]["blue"]], dtype=np.float32)
    safe_tgt = np.maximum(tgt_avg, 1.0)
    raw_gains = ref_avg / safe_tgt
    blended = 1.0 + ((raw_gains - 1.0) * float(strength))
    clamped = [_clamp_float(value, 0.5, 1.5) for value in blended]
    exposure_delta = float(reference["luma_video_level_ire"]["p50"]) - float(target["luma_video_level_ire"]["p50"])
    balance_delta = {
        channel: round(float(reference["rgb_balance"][channel]) - float(target["rgb_balance"][channel]), 6)
        for channel in ("red", "green", "blue")
    }
    return {
        "route": "api_native_color_page_shot_match_analyze",
        "region": region,
        "strength": round(float(strength), 6),
        "reference": reference,
        "target": target,
        "delta": {
            "exposure_p50_ire": round(exposure_delta, 3),
            "rgb_balance": balance_delta,
        },
        "recommended_primary": {
            "gain_r": round(float(clamped[0]), 6),
            "gain_g": round(float(clamped[1]), 6),
            "gain_b": round(float(clamped[2]), 6),
            "raw_gain_r": round(float(raw_gains[0]), 6),
            "raw_gain_g": round(float(raw_gains[1]), 6),
            "raw_gain_b": round(float(raw_gains[2]), 6),
            "clamped": any(abs(float(blended[index]) - clamped[index]) > 0.000001 for index in range(3)),
        },
        "match_strategy": "anchor_rgb_gain" if anchor_x is not None and anchor_y is not None else "global_rgb_gain",
    }


def _compare_before_after_pixels(before_rgb, after_rgb) -> dict[str, object]:
    import numpy as np

    if before_rgb.shape != after_rgb.shape:
        raise ValidationError(
            "Color Page before/after frames must have the same dimensions for pixel comparison.",
            details={
                "before_shape": [int(value) for value in before_rgb.shape],
                "after_shape": [int(value) for value in after_rgb.shape],
            },
            recoverability="manual",
        )

    before_i = before_rgb.astype(np.int16)
    after_i = after_rgb.astype(np.int16)
    diff = np.abs(after_i - before_i)
    changed_mask = np.any(diff > 0, axis=2)
    changed_pixel_count = int(np.count_nonzero(changed_mask))
    pixel_count = int(before_rgb.shape[0] * before_rgb.shape[1])
    bbox = None
    if changed_pixel_count:
        ys, xs = np.where(changed_mask)
        bbox = {
            "left": int(xs.min()),
            "top": int(ys.min()),
            "right": int(xs.max()),
            "bottom": int(ys.max()),
        }

    return {
        "frame": {"width": int(before_rgb.shape[1]), "height": int(before_rgb.shape[0]), "pixel_count": pixel_count},
        "changed_pixel_count": changed_pixel_count,
        "changed_pixel_percent": round((changed_pixel_count / pixel_count) * 100.0, 6) if pixel_count else 0.0,
        "max_channel_abs_diff": int(np.max(diff)) if diff.size else 0,
        "mean_abs_diff": round(float(np.mean(diff)), 6) if diff.size else 0.0,
        "mean_abs_diff_percent": round((float(np.mean(diff)) / 255.0) * 100.0, 6) if diff.size else 0.0,
        "changed_bounds": bbox,
    }


def _write_side_by_side_contact_sheet(before_path: Path, after_path: Path, output_path: Path) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        resolve_tool("ffmpeg"),
        "-y",
        "-v",
        "error",
        "-i",
        str(before_path),
        "-i",
        str(after_path),
        "-filter_complex",
        "[0:v][1:v]hstack=inputs=2[out]",
        "-map",
        "[out]",
        "-frames:v",
        "1",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0 or not output_path.is_file():
        raise APICallFailed(
            "Failed to generate Color Page before/after contact sheet.",
            details={"cmd": cmd, "returncode": proc.returncode, "stderr": (proc.stderr or "")[-2000:]},
        )
    return {
        "output_path": str(output_path),
        "visual_check_path": _workspace_relative_path(output_path),
        **_image_file_metadata(output_path),
    }


def _validate_normalized_coordinate(value: float, *, option_name: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Color Page qualifier-sample {option_name} must be a number between 0 and 1.",
            details={option_name.lstrip("-"): value},
            recoverability="not_applicable",
        ) from exc
    if not math.isfinite(normalized) or normalized < 0.0 or normalized > 1.0:
        raise ValidationError(
            f"Color Page qualifier-sample {option_name} must be between 0 and 1.",
            details={option_name.lstrip("-"): value, "minimum": 0, "maximum": 1},
            recoverability="not_applicable",
        )
    return normalized


def _validate_sample_radius(value: int) -> int:
    try:
        radius = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Color Page qualifier-sample --radius must be an integer between 0 and 200.",
            details={"radius": value},
            recoverability="not_applicable",
        ) from exc
    if radius < 0 or radius > 200:
        raise ValidationError(
            "Color Page qualifier-sample --radius must be between 0 and 200.",
            details={"radius": value, "minimum": 0, "maximum": 200},
            recoverability="not_applicable",
        )
    return radius


def _sample_qualifier_pixels(rgb, *, x: float, y: float, radius: int) -> dict[str, object]:
    import numpy as np

    height, width = int(rgb.shape[0]), int(rgb.shape[1])
    center_x = int(round(x * (width - 1)))
    center_y = int(round(y * (height - 1)))
    left = max(0, center_x - radius)
    right = min(width - 1, center_x + radius)
    top = max(0, center_y - radius)
    bottom = min(height - 1, center_y + radius)
    region = rgb[top : bottom + 1, left : right + 1, :].astype(np.float32)
    avg_rgb = np.mean(region.reshape((-1, 3)), axis=0)
    red, green, blue = [float(value) for value in avg_rgb]
    red_n, green_n, blue_n = red / 255.0, green / 255.0, blue / 255.0
    hue_hsv, sat_hsv, value_hsv = colorsys.rgb_to_hsv(red_n, green_n, blue_n)
    hue_hls, lightness_hls, sat_hls = colorsys.rgb_to_hls(red_n, green_n, blue_n)
    luma = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
    y_norm = (0.2126 * red_n) + (0.7152 * green_n) + (0.0722 * blue_n)
    cb = (blue_n - y_norm) / (2.0 * (1.0 - 0.0722))
    cr = (red_n - y_norm) / (2.0 * (1.0 - 0.2126))
    chroma = math.sqrt((cb * cb) + (cr * cr))
    hue_degrees = round(float(hue_hsv * 360.0), 3)
    vectorscope_hue = round(float((math.degrees(math.atan2(cr, cb)) + 360.0) % 360.0), 3)
    skin_line_angle = 123.0
    skin_delta = abs(((vectorscope_hue - skin_line_angle + 180.0) % 360.0) - 180.0)

    return {
        "frame": {"width": width, "height": height, "pixel_count": width * height},
        "sample": {
            "x": round(x, 6),
            "y": round(y, 6),
            "radius": radius,
            "center_pixel": {"x": center_x, "y": center_y},
            "bounds": {"left": left, "top": top, "right": right, "bottom": bottom},
            "pixel_count": int(region.shape[0] * region.shape[1]),
        },
        "rgb": {
            "red": round(red, 3),
            "green": round(green, 3),
            "blue": round(blue, 3),
            "hex": f"#{int(round(red)):02X}{int(round(green)):02X}{int(round(blue)):02X}",
        },
        "hsv": {
            "hue_degrees": hue_degrees,
            "saturation": round(float(sat_hsv), 5),
            "value": round(float(value_hsv), 5),
        },
        "hsl": {
            "hue_degrees": round(float(hue_hls * 360.0), 3),
            "saturation": round(float(sat_hls), 5),
            "lightness": round(float(lightness_hls), 5),
        },
        "waveform": {
            "luma_code_value": round(float(luma), 3),
            "luma_video_level_ire": _video_level_ire(luma),
        },
        "vectorscope": {
            "cb": round(float(cb), 5),
            "cr": round(float(cr), 5),
            "chroma": round(float(chroma), 5),
            "hue_degrees": vectorscope_hue,
            "skin_line_reference_degrees": skin_line_angle,
            "hue_to_skin_line_delta_degrees": round(float(skin_delta), 3),
        },
        "qualifier_seed": {
            "hue_center_degrees": hue_degrees,
            "saturation_center": round(float(sat_hsv), 5),
            "luma_center": round(float(luma / 255.0), 5),
        },
    }


def _validate_balance_strength(value: float) -> float:
    try:
        strength = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Color Page white-balance-picker --strength must be a number between 0 and 1.",
            details={"strength": value},
            recoverability="not_applicable",
        ) from exc
    if not math.isfinite(strength) or strength < 0.0 or strength > 1.0:
        raise ValidationError(
            "Color Page white-balance-picker --strength must be between 0 and 1.",
            details={"strength": value, "minimum": 0, "maximum": 1},
            recoverability="not_applicable",
        )
    return strength


def _white_balance_gains_from_sample(sample: dict[str, object], *, strength: float) -> dict[str, object]:
    rgb = sample.get("rgb") if isinstance(sample, dict) else None
    if not isinstance(rgb, dict):
        raise APICallFailed(
            "Color Page white balance sample did not include RGB values.",
            details={"sample": sample},
        )
    red = float(rgb.get("red") or 0.0)
    green = float(rgb.get("green") or 0.0)
    blue = float(rgb.get("blue") or 0.0)
    if max(red, green, blue) < 1.0:
        raise ValidationError(
            "Color Page white-balance-picker sample is too dark to balance reliably.",
            details={"rgb": rgb, "minimum_channel_code_value": 1.0},
            recoverability="not_applicable",
        )
    target = (red + green + blue) / 3.0

    def gain_for(channel: float) -> float:
        raw_gain = target / max(channel, 1.0)
        gain = 1.0 + ((raw_gain - 1.0) * strength)
        return round(min(max(gain, 0.1), 4.0), 6)

    gains = {
        "gain_r": gain_for(red),
        "gain_g": gain_for(green),
        "gain_b": gain_for(blue),
    }
    return {
        "target_code_value": round(float(target), 3),
        "strength": round(float(strength), 6),
        "gain_r": gains["gain_r"],
        "gain_g": gains["gain_g"],
        "gain_b": gains["gain_b"],
    }


@app.command("lut")
@handle_errors
def lut(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node: int = typer.Option(1, help="Node index"),
    path: Optional[str] = typer.Option(None, "--set", help="LUT file path to apply"),
    clear: bool = typer.Option(False, "--clear", help="Clear LUT from node"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Get, set, or clear LUT metadata on a color node."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    set_execution_engine("api_native")
    set_capability_context("color.lut_set_clear", "supported")
    if node < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"node": node, "minimum": 1},
            recoverability="not_applicable",
        )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError("Clip name must not be empty.", details={"clip": clip_name})
    normalized_path = None
    if path is not None:
        normalized_path = path.strip()
        if not normalized_path:
            raise ValidationError("LUT path must not be empty.", details={"lut_path": path})
    if clear and normalized_path is not None:
        raise ValidationError(
            "--set and --clear are mutually exclusive.",
            details={"options": ["--set", "--clear"]},
            recoverability="not_applicable",
        )

    is_mutating = clear or normalized_path is not None
    if is_mutating:
        enforce_mutation_policy(
            "color.lut_set_clear",
            intended_engine="workaround_setting",
            mutating=not is_dry_run(),
        )
    if is_dry_run() and is_mutating:
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        if clear:
            dry_run_message(f"Would clear LUT on node {node}")
        else:
            dry_run_message(f"Would apply LUT '{normalized_path}' on node {node}")
        return
    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_color_mutation_guard(conn)

    if clear:
        _node_stack_call(color_ops.clear_lut, conn, normalized_clip, node, node_stack_layer_index=node_stack_layer_index)
        readback = _node_stack_call(color_ops.get_lut_info, conn, normalized_clip, node, node_stack_layer_index=node_stack_layer_index)
        data = _mark_color_render_unverified(
            {
                "clip": normalized_clip,
                "node": node,
                "cleared": True,
                "applied": False,
                "requested_lut_path": None,
                "readback": readback,
                "readback_lut_path": readback.get("lut_path"),
                "route": "api_native_lut_clear",
            },
            readback_source="node_lut_readback",
        )
    elif normalized_path is not None:
        _node_stack_call(color_ops.set_lut, conn, normalized_clip, node, normalized_path, node_stack_layer_index=node_stack_layer_index)
        readback = _node_stack_call(color_ops.get_lut_info, conn, normalized_clip, node, node_stack_layer_index=node_stack_layer_index)
        data = _mark_color_render_unverified(
            {
                "clip": normalized_clip,
                "node": node,
                "applied": True,
                "cleared": False,
                "requested_lut_path": normalized_path,
                "readback": readback,
                "readback_lut_path": readback.get("lut_path"),
                "route": "api_native_lut_set",
            },
            readback_source="node_lut_readback",
        )
    else:
        data = _node_stack_call(color_ops.get_lut_info, conn, normalized_clip, node, node_stack_layer_index=node_stack_layer_index)
    output(data)


@app.command("cdl")
@handle_errors
def cdl(
    action_or_clip: Optional[str] = typer.Argument(
        None,
        help="Optional action ('get'/'set') or clip name",
    ),
    maybe_clip: Optional[str] = typer.Argument(
        None,
        help="Clip name when using legacy syntax: color cdl get/set <clip>",
    ),
    node: int = typer.Option(1, help="Node index"),
    slope: Optional[str] = typer.Option(None, help="Slope as 'R G B' (e.g., '1.0 0.9 0.8')"),
    offset: Optional[str] = typer.Option(None, help="Offset as 'R G B'"),
    power: Optional[str] = typer.Option(None, help="Power as 'R G B'"),
    saturation: Optional[float] = typer.Option(None, "--sat", help="Saturation"),
):
    """Set CDL values through DaVinci Resolve's native API with rendered-frame proof."""
    action = None
    clip_name = None
    if action_or_clip in {"get", "set"}:
        action = action_or_clip
        clip_name = maybe_clip
    else:
        clip_name = action_or_clip
        if maybe_clip is not None:
            raise ValidationError("Unexpected extra argument. Use: color cdl [clip] or color cdl get/set [clip]")

    option_set = any([slope, offset, power, saturation is not None])
    if action == "get" and option_set:
        raise ValidationError("CDL get cannot be combined with set options.")
    if action == "set" and not option_set:
        raise ValidationError("CDL set requires at least one option: --slope/--offset/--power/--sat")

    is_mutating = action == "set" or (action is None and option_set)
    if is_mutating:
        set_execution_engine("api_native")
        set_capability_context("color.cdl_set", "supported")
        _, cdl_requested = color_ops.validate_cdl_payload(node, slope, offset, power, saturation)
    if is_mutating:
        enforce_mutation_policy(
            "color.cdl_set",
            intended_engine="api_native",
            mutating=not is_dry_run(),
        )
    if is_dry_run() and is_mutating:
        dry_run_message(f"Would set CDL on node {node}: slope={slope} offset={offset} power={power} sat={saturation}")
        return
    conn = get_connection(require_timeline=True)

    if action == "get" or (action is None and not option_set):
        # Get CDL
        cdl_data = color_ops.get_cdl(conn, clip_name, node_index=node)
        output(cdl_data, title="CDL Values")
        return

    from ..core import project_ops

    render_proof = _begin_color_render_proof(conn, clip_name=clip_name, route="api_native_color_cdl_set")
    applied = color_ops.set_cdl(conn, clip_name, node, slope, offset, power, saturation)
    project_ops.save_current_project_if_available(conn)
    readback = color_ops.get_cdl(conn, clip_name, node_index=node)
    data = {
        "clip": clip_name,
        "node": node,
        "cdl_requested": cdl_requested,
        "applied": bool(applied),
        "route": "api_native_color_cdl_set",
        "readback": readback,
        "verification": {
            "status": "pending_render_proof",
            "route": "api_native_color_cdl_set",
            "api_call": "TimelineItem.SetCDL",
            "readback_source": readback.get("source") if isinstance(readback, dict) else None,
            "node_targeting": {
                "requested_node": node,
                "readback_node_scoped": readback.get("node_scoped") if isinstance(readback, dict) else None,
                "proof_source": "render_proof",
            },
        },
    }
    data["render_proof"] = _complete_color_render_proof(conn, render_proof, partial_result=data)
    data["verification"]["status"] = "verified"
    data["verification"]["render_proof_status"] = data["render_proof"]["status"]
    data["verification"]["render_proof_route"] = data["render_proof"]["route"]
    data["verification"]["node_targeting"]["status"] = "render_proof_verified"
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="CDL Values")


@app.command("arri-cdl-lut")
@handle_errors
def arri_cdl_lut(
    clip: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Apply DaVinci Resolve's ARRI CDL/LUT helper to a clip node graph."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    enforce_mutation_policy("color.arri_cdl_lut_helper", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would apply ARRI CDL/LUT helper to '{clip or 'current clip'}'.")
        return
    conn = get_connection(require_timeline=True)
    data = _node_stack_call(color_ops.apply_arri_cdl_lut, conn, clip, node_stack_layer_index=node_stack_layer_index)
    data["node_stack_layer_index"] = node_stack_layer_index
    if data.get("verified"):
        set_verification_status("verified")
        set_recoverability("not_applicable")
    else:
        set_verification_status("pending_manual")
        set_recoverability("manual")
    output(data, title="ARRI CDL/LUT")


@app.command("nodes")
@handle_errors
def nodes(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Show color node graph info."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    set_execution_engine("api_native")
    set_capability_context("color.node_graph_ops", "supported")
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    conn = get_connection(require_timeline=True)
    node_count = _node_stack_call(color_ops.get_num_nodes, conn, normalized_clip, node_stack_layer_index=node_stack_layer_index)
    rows = []
    for i in range(1, node_count + 1):
        row = {"index": i}
        try:
            row["label"] = _node_stack_call(color_ops.get_node_label, conn, normalized_clip, i, node_stack_layer_index=node_stack_layer_index)
        except Exception:
            row["label"] = ""
        try:
            row["lut"] = _node_stack_call(color_ops.get_node_lut, conn, normalized_clip, i, node_stack_layer_index=node_stack_layer_index)
        except Exception:
            row["lut"] = ""
        try:
            row["tools"] = _node_stack_call(color_ops.get_tools_in_node, conn, normalized_clip, i, node_stack_layer_index=node_stack_layer_index)
        except Exception:
            row["tools"] = []
        try:
            row.update(_node_stack_call(color_ops.get_node_cache_mode, conn, normalized_clip, i, node_stack_layer_index=node_stack_layer_index))
        except Exception:
            row["cache_mode"] = None
            row["mode_name"] = ""
        rows.append(row)
    output({"node_stack_layer_index": node_stack_layer_index, "node_count": node_count, "nodes": rows}, title="Color Nodes")


@app.command("inspect")
@handle_errors
def inspect(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Inspect native color state plus clip-attached Fusion grading state."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    set_execution_engine("api_native")
    set_capability_context("color.node_graph_ops", "supported")
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError("Clip name must not be empty.", details={"clip": clip_name})
    conn = get_connection(require_timeline=True)
    data = _node_stack_call(color_ops.inspect_color, conn, normalized_clip, node_stack_layer_index=node_stack_layer_index)
    output(data, title="Color Inspect")


@app.command("reset-fusion")
@handle_errors
def reset_fusion(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove Fusion grading helpers and restore a clean MediaIn -> MediaOut pipe."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    try:
        comp_index = int(comp_index)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Fusion composition index must be a positive integer.",
            details={"comp_index": comp_index},
            recoverability="not_applicable",
        ) from exc
    if comp_index < 1:
        raise ValidationError(
            "Fusion composition index must be a positive integer.",
            details={"comp_index": comp_index},
            recoverability="not_applicable",
        )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        conn = get_connection(require_timeline=True)
        data = color_ops.preview_reset_fusion_grading(conn, normalized_clip, comp_index=comp_index)
        output(data, title="Fusion Reset Preview")
        return
    require_force_for_machine_mode(
        force=force,
        action="color.reset_fusion",
        target_kind="fusion_grading_comp",
        target_name=normalized_clip or "current_clip",
        prompt=f"Reset Fusion grading helpers for '{normalized_clip or 'current clip'}'?",
        details={"comp_index": comp_index},
    )
    conn = get_connection(require_timeline=True)
    data = color_ops.reset_fusion_grading(conn, normalized_clip, comp_index=comp_index)
    output(data, title="Fusion Reset")


node_app = typer.Typer(help="Color node graph operations.")
app.add_typer(node_app, name="node")


@node_app.command("list")
@handle_errors
def node_list(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """List color nodes for a clip."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    conn = get_connection(require_timeline=True)
    node_count = _node_stack_call(color_ops.get_num_nodes, conn, clip_name, node_stack_layer_index=node_stack_layer_index)
    rows = []
    for i in range(1, node_count + 1):
        row = {"index": i}
        try:
            row["label"] = _node_stack_call(color_ops.get_node_label, conn, clip_name, i, node_stack_layer_index=node_stack_layer_index)
        except Exception:
            row["label"] = ""
        try:
            row["lut"] = _node_stack_call(color_ops.get_node_lut, conn, clip_name, i, node_stack_layer_index=node_stack_layer_index)
        except Exception:
            row["lut"] = ""
        try:
            mode = _node_stack_call(color_ops.get_node_cache_mode, conn, clip_name, i, node_stack_layer_index=node_stack_layer_index)
            row["cache_mode"] = mode.get("cache_mode")
            row["cache_name"] = mode.get("mode_name")
        except Exception:
            row["cache_mode"] = None
            row["cache_name"] = ""
        rows.append(row)
    output(
        {"node_stack_layer_index": node_stack_layer_index, "items": rows},
        columns=[("index", "#"), ("label", "Label"), ("lut", "LUT"), ("cache_mode", "Cache"), ("cache_name", "Cache Name")],
        title="Color Nodes",
    )


@node_app.command("lut-set")
@handle_errors
def node_lut_set(
    node_index: int = typer.Argument(..., help="1-based node index"),
    lut_path: str = typer.Argument(..., help="LUT path"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Set LUT on a color node."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    enforce_mutation_policy("color.node_graph_ops", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    _node_stack_call(color_ops.set_node_lut, conn, clip_name, node_index, lut_path, node_stack_layer_index=node_stack_layer_index)
    success(f"Set LUT on node {node_index}: {lut_path}")


@node_app.command("lut-get")
@handle_errors
def node_lut_get(
    node_index: int = typer.Argument(..., help="1-based node index"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Get LUT path from a color node."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    set_execution_engine("api_native")
    set_capability_context("color.node_graph_ops", "supported")
    if node_index < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"clip": clip_name, "node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    conn = get_connection(require_timeline=True)
    _node_stack_call(color_ops.validate_node_index, conn, normalized_clip, node_index, node_stack_layer_index=node_stack_layer_index)
    lut_path = _node_stack_call(color_ops.get_node_lut, conn, normalized_clip, node_index, node_stack_layer_index=node_stack_layer_index)
    output({"node_stack_layer_index": node_stack_layer_index, "node_index": node_index, "lut_path": lut_path})


@node_app.command("label-get")
@handle_errors
def node_label_get(
    node_index: int = typer.Argument(..., help="1-based node index"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Get label for a color node."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    set_execution_engine("api_native")
    set_capability_context("color.node_graph_ops", "supported")
    if node_index < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"clip": clip_name, "node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    conn = get_connection(require_timeline=True)
    _node_stack_call(color_ops.validate_node_index, conn, normalized_clip, node_index, node_stack_layer_index=node_stack_layer_index)
    label = _node_stack_call(color_ops.get_node_label, conn, normalized_clip, node_index, node_stack_layer_index=node_stack_layer_index)
    output({"node_stack_layer_index": node_stack_layer_index, "node_index": node_index, "label": label})


@node_app.command("label-set")
@handle_errors
def node_label_set(
    node_index: int = typer.Argument(..., help="1-based node index"),
    label: str = typer.Argument(..., help="Label to assign to the node"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Set label for a color node via native SetNodeLabel or verified DB fallback."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    set_execution_engine("api_native")
    set_capability_context("color.node_graph_ops", "supported")
    if node_index < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"clip": clip_name, "node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    enforce_mutation_policy(
        "color.node_graph_ops",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_color_mutation_guard(conn)
    _node_stack_call(color_ops.validate_node_index, conn, normalized_clip, node_index, node_stack_layer_index=node_stack_layer_index)
    if is_dry_run():
        dry_run_message(f"Would set node {node_index} label to '{label}'")
        return
    try:
        _node_stack_call(color_ops.set_node_label, conn, normalized_clip, node_index, label, node_stack_layer_index=node_stack_layer_index)
    except CapabilityNegotiationFailed as exc:
        details = getattr(exc, "details", {}) or {}
        if details.get("required_method") != "SetNodeLabel":
            raise
        if node_stack_layer_index != 1:
            raise
        from ..core import color_page_db

        set_execution_engine("db_workaround")
        data = color_page_db.write_node_label(
            conn,
            clip_name=normalized_clip,
            node_index=node_index,
            label=label,
        )
        data["message"] = f"Set node {node_index} label to: {label}"
        output(data)
        return
    success(f"Set node {node_index} label to: {label}")


@node_app.command("tools")
@handle_errors
def node_tools(
    node_index: int = typer.Argument(..., help="1-based node index"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """List tools/effects present inside a color node."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    set_execution_engine("api_native")
    set_capability_context("color.node_graph_ops", "supported")
    if node_index < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"clip": clip_name, "node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    conn = get_connection(require_timeline=True)
    _node_stack_call(color_ops.validate_node_index, conn, normalized_clip, node_index, node_stack_layer_index=node_stack_layer_index)
    tools = _node_stack_call(color_ops.get_tools_in_node, conn, normalized_clip, node_index, node_stack_layer_index=node_stack_layer_index)
    output({"node_stack_layer_index": node_stack_layer_index, "node_index": node_index, "tools": tools}, title=f"Node {node_index} Tools")


@node_app.command("graph")
@handle_errors
def node_graph(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Return full node-graph summary with labels, LUTs, tools, and cache modes."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    conn = get_connection(require_timeline=True)
    node_count = _node_stack_call(color_ops.get_num_nodes, conn, clip_name, node_stack_layer_index=node_stack_layer_index)
    rows = []
    for i in range(1, node_count + 1):
        row = {"index": i}
        try:
            row["label"] = _node_stack_call(color_ops.get_node_label, conn, clip_name, i, node_stack_layer_index=node_stack_layer_index)
        except Exception:
            row["label"] = ""
        try:
            row["lut"] = _node_stack_call(color_ops.get_node_lut, conn, clip_name, i, node_stack_layer_index=node_stack_layer_index)
        except Exception:
            row["lut"] = ""
        try:
            row["tools"] = _node_stack_call(color_ops.get_tools_in_node, conn, clip_name, i, node_stack_layer_index=node_stack_layer_index)
        except Exception:
            row["tools"] = []
        try:
            row.update(_node_stack_call(color_ops.get_node_cache_mode, conn, clip_name, i, node_stack_layer_index=node_stack_layer_index))
        except Exception:
            row["cache_mode"] = None
            row["mode_name"] = ""
        rows.append(row)
    output({"node_stack_layer_index": node_stack_layer_index, "node_count": node_count, "nodes": rows}, title="Color Node Graph")


@node_app.command("enable")
@handle_errors
def node_enable(
    node_index: int = typer.Argument(..., help="1-based node index"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Enable a color node."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    set_execution_engine("api_native")
    set_capability_context("color.node_graph_ops", "supported")
    if node_index < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"clip": clip_name, "node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    enforce_mutation_policy(
        "color.node_graph_ops",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_timeline=True)
    _node_stack_call(color_ops.validate_node_index, conn, normalized_clip, node_index, node_stack_layer_index=node_stack_layer_index)
    if is_dry_run():
        dry_run_message(f"Would enable node {node_index}")
        return
    _node_stack_call(color_ops.set_node_enabled, conn, normalized_clip, node_index, True, node_stack_layer_index=node_stack_layer_index)
    success(f"Enabled node {node_index}.")


@node_app.command("disable")
@handle_errors
def node_disable(
    node_index: int = typer.Argument(..., help="1-based node index"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Disable a color node."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    set_execution_engine("api_native")
    set_capability_context("color.node_graph_ops", "supported")
    if node_index < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"clip": clip_name, "node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    enforce_mutation_policy(
        "color.node_graph_ops",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_timeline=True)
    _node_stack_call(color_ops.validate_node_index, conn, normalized_clip, node_index, node_stack_layer_index=node_stack_layer_index)
    if is_dry_run():
        dry_run_message(f"Would disable node {node_index}")
        return
    _node_stack_call(color_ops.set_node_enabled, conn, normalized_clip, node_index, False, node_stack_layer_index=node_stack_layer_index)
    success(f"Disabled node {node_index}.")


@node_app.command("cache")
@handle_errors
def node_cache(
    node_index: int = typer.Argument(..., help="1-based node index"),
    mode: Optional[int] = typer.Option(None, "--mode", help="-1=auto, 0=disabled, 1=enabled"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
):
    """Get or set node cache mode."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    set_execution_engine("api_native")
    set_capability_context("color.node_graph_ops", "supported")
    if node_index < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"clip": clip_name, "node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError("Clip name must not be empty.", details={"clip": clip_name})
    if mode is not None and mode not in (-1, 0, 1):
        raise ValidationError(
            "Invalid cache mode.",
            details={"cache_value": mode, "allowed": [-1, 0, 1]},
            recoverability="not_applicable",
        )
    if mode is not None:
        enforce_mutation_policy("color.node_graph_ops", intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_timeline=True)
    _node_stack_call(color_ops.validate_node_index, conn, normalized_clip, node_index, node_stack_layer_index=node_stack_layer_index)
    if mode is None:
        data = _node_stack_call(color_ops.get_node_cache_mode, conn, normalized_clip, node_index, node_stack_layer_index=node_stack_layer_index)
        output({"node_stack_layer_index": node_stack_layer_index, "node_index": node_index, **data})
        return
    if is_dry_run():
        dry_run_message(f"Would set node {node_index} cache mode to {mode}")
        return
    _node_stack_call(color_ops.set_node_cache_mode, conn, normalized_clip, node_index, mode, node_stack_layer_index=node_stack_layer_index)
    success(f"Set node {node_index} cache mode to {mode}.")


@node_app.command("reset")
@handle_errors
def node_reset(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, help="One-based node-stack layer index"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Reset all grades on node graph."""
    node_stack_layer_index = _node_stack_layer(node_stack_layer_index)
    enforce_mutation_policy("color.node_graph_ops", intended_engine="api_native")
    require_force_for_machine_mode(
        force=force,
        action="color.node.reset",
        target_kind="color_node_graph",
        target_name=clip_name or "current_clip",
        prompt=f"Reset all grades for '{clip_name or 'current clip'}'?",
    )
    conn = get_connection(require_timeline=True)
    _node_stack_call(color_ops.reset_all_grades, conn, clip_name, node_stack_layer_index=node_stack_layer_index)
    success("Reset all grades.")
