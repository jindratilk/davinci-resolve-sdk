"""Transforms helpers for Color Page DB operations."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import sqlite3
import struct
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from ...errors import APICallFailed, ValidationError
from ..db_session import DiskDbMutationSession, execute_sqlite_disk_db_mutation
from ..db_timeline_rows import find_ti_item_row
from .constants import *
from .proto_codec import *
from .version_body import *


# ---------------------------------------------------------------------------
# CDL ↔ DaVinci Resolve internal value transforms (verified 2026-04-04)
# ---------------------------------------------------------------------------

def cdl_offset_to_lift(cdl_offset: float, cdl_slope: float) -> float:
    """Convert CDL Offset + Slope → DaVinci Resolve internal Lift value.

    Formula: Lift = Offset / (Slope + Offset)
    When Offset ≈ 0: Lift ≈ 0
    """
    denom = cdl_slope + cdl_offset
    if abs(denom) < 1e-10:
        return 0.0
    return cdl_offset / denom


def cdl_slope_to_gain(cdl_slope: float, cdl_offset: float = 0.0) -> float:
    """Convert CDL Slope + Offset → DaVinci Resolve internal Gain value.

    Formula: Gain = Slope / (1 - Offset)  (when Offset != 0)
              Gain = Slope                 (when Offset = 0)
    """
    if abs(cdl_offset) < 1e-10:
        return cdl_slope
    return cdl_slope / (1.0 - cdl_offset)


def cdl_power_to_gamma(cdl_power: float) -> float:
    """Convert CDL Power → DaVinci Resolve internal Gamma value.

    Formula:
      Power >= 1: Gamma = -(Power - 1)
      Power <  1: Gamma = 1/Power - 1

    Default (Power=1.0) → Gamma=0.0
    """
    if abs(cdl_power - 1.0) < 1e-10:
        return 0.0
    if cdl_power >= 1.0:
        return -(cdl_power - 1.0)
    return 1.0 / cdl_power - 1.0


def lift_to_cdl_offset(lift: float, gain: float = 1.0) -> float:
    """Convert DaVinci Resolve internal Lift → CDL Offset.

    Reverse of:
      Lift = Offset / (Slope + Offset)
      Gain = Slope / (1 - Offset)
    """
    if abs(lift) < 1e-10:
        return 0.0
    denom = 1.0 - lift + (lift * gain)
    if abs(denom) < 1e-10:
        return 0.0
    return (lift * gain) / denom


def gain_to_cdl_slope(gain: float, offset: float = 0.0) -> float:
    """Convert DaVinci Resolve internal Gain → CDL Slope.

    Reverse of Gain = Slope / (1 - Offset).
    """
    return gain * (1.0 - offset)


def gamma_to_cdl_power(gamma: float) -> float:
    """Convert DaVinci Resolve internal Gamma → CDL Power.

    Reverse of cdl_power_to_gamma:
      Gamma <= 0: Power = 1 - Gamma
      Gamma >  0: Power = 1 / (1 + Gamma)
    """
    if abs(gamma) < 1e-10:
        return 1.0
    if gamma <= 0:
        return 1.0 - gamma
    return 1.0 / (1.0 + gamma)


def curve_endpoint_ui_to_internal(value: float) -> float:
    """Convert DaVinci Resolve Custom Curves Edit UI value (0-100) to DB float."""
    if value < 0.0 or value > 100.0:
        raise ValidationError(
            "Custom curve endpoint values must be between 0 and 100.",
            details={"value": value, "minimum": 0, "maximum": 100},
            recoverability="not_applicable",
        )
    return (value - 50.0) / 50.0


def curve_endpoint_internal_to_ui(value: float) -> float:
    """Convert DaVinci Resolve Custom Curves DB float to UI value."""
    return (value * 50.0) + 50.0


__all__ = (
    'cdl_offset_to_lift',
    'cdl_slope_to_gain',
    'cdl_power_to_gamma',
    'lift_to_cdl_offset',
    'gain_to_cdl_slope',
    'gamma_to_cdl_power',
    'curve_endpoint_ui_to_internal',
    'curve_endpoint_internal_to_ui',
)
