"""Adaptive silence-gate calibration for rendered timeline audio."""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

from ..errors import APICallFailed
from ..external_tools import resolve_tool

GATE_BIAS = 0.6
MIN_SEPARATION_DB = 12.0
DIGITAL_SILENCE_HEADROOM_DB = 24.0
GATE_MIN_DB = -60.0
GATE_MAX_DB = -24.0

_RMS_TROUGH_RE = re.compile(r"RMS (?:through|trough) dB:\s*(-?[0-9.]+|-?inf)", re.IGNORECASE)
_RMS_PEAK_RE = re.compile(r"RMS peak dB:\s*(-?[0-9.]+|-?inf)", re.IGNORECASE)


@dataclass(frozen=True)
class SilenceCalibration:
    gate_db: float
    basis: str
    usable: bool
    quiet_rms_db: Optional[float] = None
    loud_rms_db: Optional[float] = None
    separation_db: Optional[float] = None
    reason: Optional[str] = None

    def as_dict(self) -> dict:
        def finite(value: Optional[float]) -> Optional[float]:
            if value is None or not math.isfinite(value):
                return None
            return round(value, 2)

        return {
            "gate_db": round(self.gate_db, 2),
            "basis": self.basis,
            "usable": self.usable,
            "quiet_rms_db": finite(self.quiet_rms_db),
            "loud_rms_db": finite(self.loud_rms_db),
            "quiet_is_digital_silence": self.quiet_rms_db == float("-inf"),
            "separation_db": finite(self.separation_db),
            "reason": self.reason,
        }


def _parse_level(value: str) -> float:
    normalized = value.strip().lower()
    if normalized.endswith("inf"):
        return float("-inf") if normalized.startswith("-") else float("inf")
    return float(normalized)


def parse_astats_levels(stderr: str) -> tuple[Optional[float], Optional[float]]:
    trough_matches = _RMS_TROUGH_RE.findall(stderr)
    peak_matches = _RMS_PEAK_RE.findall(stderr)
    quiet = _parse_level(trough_matches[-1]) if trough_matches else None
    loud = _parse_level(peak_matches[-1]) if peak_matches else None
    return quiet, loud


def gate_from_levels(
    quiet_rms_db: Optional[float],
    loud_rms_db: Optional[float],
    *,
    fallback_gate_db: float,
) -> SilenceCalibration:
    def unusable(reason: str, separation_db: Optional[float] = None) -> SilenceCalibration:
        return SilenceCalibration(
            gate_db=fallback_gate_db,
            basis="unusable",
            usable=False,
            quiet_rms_db=quiet_rms_db,
            loud_rms_db=loud_rms_db,
            separation_db=separation_db,
            reason=reason,
        )

    if quiet_rms_db is None or loud_rms_db is None:
        return unusable("ffmpeg astats did not report usable RMS trough and peak levels")
    if not math.isfinite(loud_rms_db):
        return unusable("the rendered timeline carries no programme audio")
    if quiet_rms_db == float("-inf"):
        gate = min(max(loud_rms_db - DIGITAL_SILENCE_HEADROOM_DB, GATE_MIN_DB), GATE_MAX_DB)
        return SilenceCalibration(
            gate_db=gate,
            basis="digital_silence",
            usable=True,
            quiet_rms_db=quiet_rms_db,
            loud_rms_db=loud_rms_db,
            separation_db=float("inf"),
            reason="true digital silence is present",
        )
    if not math.isfinite(quiet_rms_db):
        return unusable("the rendered timeline has an invalid quiet-level measurement")

    separation = loud_rms_db - quiet_rms_db
    if separation < MIN_SEPARATION_DB:
        return unusable(
            f"quietest and loudest RMS windows are only {separation:.1f} dB apart",
            separation,
        )

    gate = quiet_rms_db + GATE_BIAS * separation
    gate = min(max(gate, GATE_MIN_DB), GATE_MAX_DB)
    return SilenceCalibration(
        gate_db=gate,
        basis="measured_dynamics",
        usable=True,
        quiet_rms_db=quiet_rms_db,
        loud_rms_db=loud_rms_db,
        separation_db=separation,
    )


def calibrate_rendered_audio(path: str, *, fallback_gate_db: float) -> SilenceCalibration:
    command = [
        resolve_tool("ffmpeg"),
        "-hide_banner",
        "-nostats",
        "-i",
        path,
        "-vn",
        "-af",
        "astats",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise APICallFailed(
            "ffmpeg silence calibration failed.",
            details={"stderr_tail": proc.stderr[-500:], "audio_path": path},
        )
    return gate_from_levels(*parse_astats_levels(proc.stderr), fallback_gate_db=fallback_gate_db)
