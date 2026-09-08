"""Bounded cubic Bézier calculations for retime readback and inverse proof."""
from __future__ import annotations

import math
from typing import Sequence

from ..errors import APICallFailed


def bezier_value(controls: Sequence[float], t: float) -> float:
    a, b, c, d = controls
    u = 1.0 - t
    return u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d


def bezier_roots(controls: Sequence[float], target: float) -> list[float]:
    """Find every unit-interval root, including extrema and equal-endpoint humps."""
    if len(controls) != 4 or not all(math.isfinite(v) for v in (*controls, target)):
        raise APICallFailed("Retime reference mapping contains invalid coordinates.")
    scale = max(abs(v) for v in (*controls, target)) or 1.0
    values = tuple(v / scale for v in controls)
    target = target / scale
    a, b, c, d = values
    qa, qb, qc = -a + 3 * b - 3 * c + d, 2 * (a - 2 * b + c), b - a
    cuts = [0.0, 1.0]
    if abs(qa) < 1e-14:
        if abs(qb) >= 1e-14:
            cuts.append(-qc / qb)
    else:
        discriminant = qb * qb - 4 * qa * qc
        if discriminant >= 0:
            root = math.sqrt(discriminant)
            cuts.extend(((-qb - root) / (2 * qa), (-qb + root) / (2 * qa)))
    cuts = sorted(set(t for t in cuts if 0 <= t <= 1))
    roots = [t for t in cuts if abs(bezier_value(values, t) - target) <= 1e-14]
    for low, high in zip(cuts, cuts[1:]):
        left = bezier_value(values, low) - target
        right = bezier_value(values, high) - target
        if left * right >= 0:
            continue
        for _ in range(52):
            middle = (low + high) / 2
            value = bezier_value(values, middle) - target
            if (value < 0) == (left < 0):
                low = middle
            else:
                high = middle
        roots.append((low + high) / 2)
    return sorted(set(roots))
