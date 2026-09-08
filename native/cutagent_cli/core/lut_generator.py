"""
LUT Generator — pure Python .cube 3D LUT generation.

Generates 33x33x33 3D LUT .cube files from curve points or hue/sat modifications.
No external dependencies required.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Tuple

from ..errors import ValidationError


def _interpolate_curve(points: List[Tuple[float, float]], x: float) -> float:
    """
    Linear interpolation along a curve defined by sorted (x, y) points.
    Clamps output to [0, 1].
    """
    if not points:
        return x
    if x <= points[0][0]:
        return max(0.0, min(1.0, points[0][1]))
    if x >= points[-1][0]:
        return max(0.0, min(1.0, points[-1][1]))
    
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        if x0 <= x <= x1:
            if x1 == x0:
                return max(0.0, min(1.0, y0))
            t = (x - x0) / (x1 - x0)
            return max(0.0, min(1.0, y0 + t * (y1 - y0)))
    
    return max(0.0, min(1.0, x))


def _parse_curve_points(s: str) -> List[Tuple[float, float]]:
    """Parse '0,0;0.5,0.6;1,1' into list of (x, y) tuples."""
    points = []
    for pair in s.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split(",")
        if len(parts) != 2:
            raise ValidationError(f"Invalid curve point: {pair}", details={"point": pair, "raw": s})
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError as exc:
            raise ValidationError(f"Invalid curve point: {pair}", details={"point": pair, "raw": s}) from exc
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValidationError(
                f"Curve point values must be finite: {pair}",
                details={"point": pair, "raw": s, "x": x, "y": y},
            )
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValidationError(
                f"Curve point values must be normalized between 0 and 1: {pair}",
                details={"point": pair, "raw": s, "x": x, "y": y},
            )
        points.append((x, y))
    return sorted(points, key=lambda p: p[0])


def validate_cube_output_path(output_path: str) -> str:
    path = Path(output_path).expanduser()
    parent = path.parent if path.parent != Path("") else Path(".")
    if not parent.exists():
        raise ValidationError(
            "Output directory does not exist.",
            details={"output_path": str(path), "parent": str(parent)},
            recoverability="not_applicable",
        )
    if not parent.is_dir():
        raise ValidationError(
            "Output parent path is not a directory.",
            details={"output_path": str(path), "parent": str(parent)},
            recoverability="not_applicable",
        )
    if path.exists() and path.is_dir():
        raise ValidationError(
            "Output path is a directory.",
            details={"output_path": str(path)},
            recoverability="not_applicable",
        )
    return str(path)


def _validate_cube_output_path(output_path: str) -> str:
    return validate_cube_output_path(output_path)


def validate_curves_lut_request(
    output_path: str,
    red: Optional[str] = None,
    green: Optional[str] = None,
    blue: Optional[str] = None,
    master: Optional[str] = None,
) -> str:
    """Validate curves LUT inputs without writing the output file."""
    if red:
        _parse_curve_points(red)
    if green:
        _parse_curve_points(green)
    if blue:
        _parse_curve_points(blue)
    if master:
        _parse_curve_points(master)
    return _validate_cube_output_path(output_path)


def _rgb_to_hsv(r: float, g: float, b: float) -> Tuple[float, float, float]:
    """Convert RGB [0,1] to HSV [0,360], [0,1], [0,1]."""
    mx = max(r, g, b)
    mn = min(r, g, b)
    d = mx - mn
    
    v = mx
    s = 0.0 if mx == 0 else d / mx
    
    if d == 0:
        h = 0.0
    elif mx == r:
        h = 60.0 * (((g - b) / d) % 6)
    elif mx == g:
        h = 60.0 * (((b - r) / d) + 2)
    else:
        h = 60.0 * (((r - g) / d) + 4)
    
    if h < 0:
        h += 360.0
    
    return h, s, v


def _hsv_to_rgb(h: float, s: float, v: float) -> Tuple[float, float, float]:
    """Convert HSV to RGB [0,1]."""
    h = h % 360.0
    c = v * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = v - c
    
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    
    return (
        max(0.0, min(1.0, r + m)),
        max(0.0, min(1.0, g + m)),
        max(0.0, min(1.0, b + m)),
    )


def _write_cube_header(f, title: str, size: int = 33):
    """Write .cube file header."""
    f.write(f"TITLE \"{title}\"\n")
    f.write(f"LUT_3D_SIZE {size}\n")
    f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
    f.write("DOMAIN_MAX 1.0 1.0 1.0\n")
    f.write("\n")


def generate_curves_lut(
    output_path: str,
    red: Optional[str] = None,
    green: Optional[str] = None,
    blue: Optional[str] = None,
    master: Optional[str] = None,
    size: int = 33,
) -> str:
    """
    Generate a .cube 3D LUT from RGB curve points.
    
    Args:
        output_path: Output .cube file path
        red: Red curve points as '0,0;0.5,0.6;1,1'
        green: Green curve points
        blue: Blue curve points
        master: Master (all channels) curve points
        size: LUT size (default 33)
    
    Returns:
        Output file path
    """
    output_path = validate_curves_lut_request(
        output_path=output_path,
        red=red,
        green=green,
        blue=blue,
        master=master,
    )
    identity = [(0.0, 0.0), (1.0, 1.0)]
    
    r_curve = _parse_curve_points(red) if red else identity
    g_curve = _parse_curve_points(green) if green else identity
    b_curve = _parse_curve_points(blue) if blue else identity
    m_curve = _parse_curve_points(master) if master else identity
    
    with open(output_path, "w") as f:
        _write_cube_header(f, "Curves LUT", size)
        
        for bi in range(size):
            for gi in range(size):
                for ri in range(size):
                    r = ri / (size - 1)
                    g = gi / (size - 1)
                    b = bi / (size - 1)
                    
                    # Apply master curve first, then per-channel
                    r = _interpolate_curve(m_curve, r)
                    g = _interpolate_curve(m_curve, g)
                    b = _interpolate_curve(m_curve, b)
                    
                    r = _interpolate_curve(r_curve, r)
                    g = _interpolate_curve(g_curve, g)
                    b = _interpolate_curve(b_curve, b)
                    
                    f.write(f"{r:.6f} {g:.6f} {b:.6f}\n")
    
    return output_path


def generate_hue_sat_lut(
    output_path: str,
    hue_shift: float = 0.0,
    sat_boost: float = 1.0,
    val_boost: float = 1.0,
    size: int = 33,
) -> str:
    """
    Generate a .cube 3D LUT from hue/sat/val modifications.
    
    Args:
        output_path: Output .cube file path
        hue_shift: Hue rotation in degrees
        sat_boost: Saturation multiplier (1.0 = no change)
        val_boost: Value/brightness multiplier (1.0 = no change)
        size: LUT size (default 33)
    
    Returns:
        Output file path
    """
    output_path = validate_huesat_lut_request(
        output_path=output_path,
        hue_shift=hue_shift,
        sat_boost=sat_boost,
        val_boost=val_boost,
    )
    with open(output_path, "w") as f:
        _write_cube_header(f, "HueSat LUT", size)
        
        for bi in range(size):
            for gi in range(size):
                for ri in range(size):
                    r = ri / (size - 1)
                    g = gi / (size - 1)
                    b = bi / (size - 1)
                    
                    h, s, v = _rgb_to_hsv(r, g, b)
                    
                    h = (h + hue_shift) % 360.0
                    s = max(0.0, min(1.0, s * sat_boost))
                    v = max(0.0, min(1.0, v * val_boost))
                    
                    r2, g2, b2 = _hsv_to_rgb(h, s, v)
                    f.write(f"{r2:.6f} {g2:.6f} {b2:.6f}\n")
    
    return output_path


def validate_huesat_lut_request(
    output_path: str,
    hue_shift: float = 0.0,
    sat_boost: float = 1.0,
    val_boost: float = 1.0,
) -> str:
    """Validate hue/saturation LUT inputs without writing the output file."""
    values = {
        "hue_shift": hue_shift,
        "sat_boost": sat_boost,
        "val_boost": val_boost,
    }
    for name, value in values.items():
        if not math.isfinite(float(value)):
            raise ValidationError(
                "Hue/saturation LUT values must be finite.",
                details={"parameter": name, "value": value},
            )
    return _validate_cube_output_path(output_path)
