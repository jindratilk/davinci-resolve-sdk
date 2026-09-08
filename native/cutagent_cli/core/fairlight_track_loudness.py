"""Measured normalization for one exact Fairlight audio track.

The route isolates the signed track only while rendering measurement PCM,
restores every track-enabled state, writes the verified track fader, and then
measures the same complete occupied range again.  It never substitutes a
requested gain for measured loudness.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import time
import wave
from array import array
from pathlib import Path
from typing import Any, Mapping

from ..fairlight_prepared_evaluation import FairlightEvaluationError


TOLERANCE_LUFS = 0.3


def _file_sha256(file: Path) -> str:
    digest = hashlib.sha256()
    try:
        with file.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Track loudness PCM cannot be hashed."
        ) from exc
    return digest.hexdigest()


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise FairlightEvaluationError("VERIFICATION_FAILED", f"Invalid {label}.")
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = float("nan")
    if not math.isfinite(result):
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED",
            f"Non-finite {label}; silence cannot establish track loudness.",
        )
    return result


def _inspect_pcm(
    file: Path,
    *,
    expected_duration_seconds: float,
) -> dict[str, Any]:
    """Inspect complete 16-bit PCM without loading the render into memory."""
    digest = _file_sha256(file)
    try:
        with wave.open(str(file), "rb") as pcm:
            rate = pcm.getframerate()
            count = pcm.getnframes()
            channels = pcm.getnchannels()
            sample_width = pcm.getsampwidth()
            if (
                rate <= 0
                or count <= 0
                or channels <= 0
                or sample_width != 2
                or pcm.getcomptype() != "NONE"
            ):
                raise FairlightEvaluationError(
                    "VERIFICATION_FAILED",
                    "Track loudness requires nonempty 16-bit decoded PCM.",
                )
            if abs(count / rate - expected_duration_seconds) > max(0.002, 2 / rate):
                raise FairlightEvaluationError(
                    "VERIFICATION_FAILED",
                    "Track loudness PCM does not cover the exact bound duration.",
                )
            remaining = count
            peak_sample = 0
            while remaining:
                frames = min(remaining, 65536)
                chunk = pcm.readframes(frames)
                if len(chunk) != frames * channels * sample_width:
                    raise FairlightEvaluationError(
                        "VERIFICATION_FAILED", "Track loudness PCM is truncated."
                    )
                values = array("h")
                values.frombytes(chunk)
                if sys.byteorder != "little":
                    values.byteswap()
                peak_sample = max(peak_sample, max((abs(value) for value in values), default=0))
                remaining -= frames
    except (OSError, wave.Error, EOFError) as exc:
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Track loudness PCM is not decodable."
        ) from exc

    if _file_sha256(file) != digest:
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Track loudness PCM changed during inspection."
        )
    return {
        "pcmSha256": digest,
        "sampleFrames": count,
        "sampleRate": rate,
        "pcmPeakSampleAbs": peak_sample,
    }


def measure_pcm(
    file: Path,
    *,
    expected_duration_seconds: float,
    ffmpeg: str,
) -> dict[str, Any]:
    """Measure one complete, immutable PCM render with ffmpeg loudnorm."""
    inspected = _inspect_pcm(
        file, expected_duration_seconds=expected_duration_seconds
    )
    digest = inspected["pcmSha256"]
    completed = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-nostats",
            "-i",
            str(file),
            "-af",
            "loudnorm=I=-14:TP=-1.5:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    text = completed.stderr
    if completed.returncode != 0 or len(text) > 1_048_576:
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Exact track loudness measurement failed."
        )
    try:
        payload = json.loads(text[text.rindex("{") : text.rindex("}") + 1])
        integrated = _number(payload["input_i"], "integrated loudness")
        peak = _number(payload["input_tp"], "true peak")
    except (ValueError, KeyError) as exc:
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Track loudness measurement is incomplete."
        ) from exc
    if _file_sha256(file) != digest:
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Track loudness PCM changed during measurement."
        )
    return {
        "integratedLufs": integrated,
        "truePeakDbtp": peak,
        **inspected,
    }


def verify_target_source(
    measured: Mapping[str, Any], control: Mapping[str, Any]
) -> None:
    """Prove that target enablement, rather than an inherited selector, sources PCM."""
    measured_peak = measured.get("pcmPeakSampleAbs")
    control_peak = control.get("pcmPeakSampleAbs")
    if (
        measured.get("sampleFrames") != control.get("sampleFrames")
        or measured.get("sampleRate") != control.get("sampleRate")
        or not isinstance(measured_peak, int)
        or not isinstance(control_peak, int)
        or control_peak > 4
        or measured_peak < 64
        or measured_peak <= control_peak * 128
    ):
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Rendered PCM does not prove that the exact isolated target track is its audio source.",
        )


def plan_fader(
    before: Mapping[str, Any], current_fader_db: float, request: Mapping[str, Any]
) -> float:
    """Plan the bounded track-fader value; fail when a limiter is required."""
    from . import fairlight_ops

    integrated = _number(before.get("integratedLufs"), "integrated loudness")
    peak = _number(before.get("truePeakDbtp"), "true peak")
    target = _number(request.get("integratedLufs"), "requested loudness")
    ceiling = _number(request.get("truePeakDbtp"), "requested true peak")
    planned = fairlight_ops.validate_mixer_fader_level(
        current_fader_db + target - integrated
    )
    delta = planned - current_fader_db
    if peak + delta > ceiling or abs(integrated + delta - target) > TOLERANCE_LUFS:
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Requested track loudness and true-peak ceiling require processing beyond the verified fader route.",
        )
    return planned


def verify_measurement(value: Mapping[str, Any], request: Mapping[str, Any]) -> None:
    if (
        abs(
            _number(value.get("integratedLufs"), "integrated loudness")
            - _number(request.get("integratedLufs"), "requested loudness")
        )
        > TOLERANCE_LUFS
        or _number(value.get("truePeakDbtp"), "true peak")
        > _number(request.get("truePeakDbtp"), "requested true peak")
    ):
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED",
            "Native isolated-track PCM did not meet both requested loudness and true-peak bounds.",
        )


def _connection(binding: Mapping[str, Any]):
    from ..commands import clip

    connection = clip.get_connection(require_timeline=True)
    project_get_id = getattr(connection.project, "GetUniqueId", None)
    timeline_get_id = getattr(connection.timeline, "GetUniqueId", None)
    try:
        project_id = str(project_get_id()) if callable(project_get_id) else None
        timeline_id = str(timeline_get_id()) if callable(timeline_get_id) else None
    except Exception:
        project_id = timeline_id = None
    if (
        project_id != binding["nativeProjectId"]
        or timeline_id != binding["nativeTimelineId"]
    ):
        raise FairlightEvaluationError(
            "STALE_REVISION", "Track loudness project or timeline custody changed."
        )
    return connection


def _read_fader(binding: Mapping[str, Any], *, flush: bool = False) -> float:
    from . import fairlight_ops

    connection = _connection(binding)
    if flush:
        save = getattr(connection.project_manager, "SaveProject", None)
        if not callable(save) or save() is False:
            raise FairlightEvaluationError(
                "CAPABILITY_NEGOTIATION_FAILED",
                "Exact track fader custody requires a saved Disk project.",
            )
        time.sleep(5.0)
    state = fairlight_ops.read_audio_track_fader_db(
        connection, index=binding["trackIndex"]
    )
    value = state.get("level_db")
    if value is None:
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Exact track loudness requires one common fader level across every target channel lane.",
        )
    return _number(value, "track fader")


def _set_fader(binding: Mapping[str, Any], level_db: float) -> None:
    from . import fairlight_ops

    result = fairlight_ops.set_audio_track_fader_db(
        _connection(binding), index=binding["trackIndex"], level_db=level_db
    )
    verification = result.get("verification") if isinstance(result, Mapping) else None
    checks = verification.get("checks") if isinstance(verification, Mapping) else None
    if (
        not isinstance(verification, Mapping)
        or verification.get("status") != "verified"
        or not isinstance(checks, list)
        or not checks
        or any(
            not isinstance(check, Mapping) or check.get("ok") is not True
            for check in checks
        )
        or _read_fader(binding) != level_db
    ):
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Track fader write lacks exact native readback."
        )


def _restore_fader(binding: Mapping[str, Any], expected: float, owned: float) -> None:
    current = _read_fader(binding, flush=True)
    if current == expected:
        return
    if current != owned:
        raise FairlightEvaluationError(
            "STALE_REVISION",
            "Track loudness recovery no longer owns the current fader value.",
        )
    _set_fader(binding, expected)


def _render_isolated(
    binding: Mapping[str, Any], path: Path, *, ffmpeg: str, target_enabled: bool = True
) -> dict[str, Any]:
    from . import fairlight_ops, render_engine

    connection = _connection(binding)
    count = fairlight_ops._audio_track_count(connection)
    index = binding["trackIndex"]
    if not isinstance(count, int) or index < 1 or index > count:
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED", "Exact loudness target track is unavailable."
        )
    states = [
        {
            "index": current,
            "enabled": fairlight_ops._read_audio_track_enabled_strict(
                connection, current
            ),
        }
        for current in range(1, count + 1)
    ]
    if not states[index - 1]["enabled"]:
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "A disabled track cannot establish final program loudness.",
        )
    try:
        for current in range(1, count + 1):
            fairlight_ops._set_audio_track_enabled(
                connection, current, target_enabled and current == index
            )
        actual = Path(
            render_engine.render_audio_range(
                connection,
                str(path),
                mark_in_frame=binding["startFrame"],
                mark_out_frame=binding["endExclusiveFrame"] - 1,
            )
        )
        if actual != path:
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED",
                "Track loudness PCM escaped its carrier-owned path.",
            )
    finally:
        fairlight_ops.restore_audio_track_states(connection, states)
    rate = binding["frameRate"]
    duration = (
        (binding["endExclusiveFrame"] - binding["startFrame"])
        * rate["denominator"]
        / rate["numerator"]
    )
    if target_enabled:
        return measure_pcm(path, expected_duration_seconds=duration, ffmpeg=ffmpeg)
    return _inspect_pcm(path, expected_duration_seconds=duration)


def execute(
    context: Mapping[str, Any],
    binding: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Measure, mutate, and remeasure one signed track with owned recovery."""
    from . import audio_ops

    artifact = (
        context.get("privateBindings", {})
        .get("fairlight", {})
        .get("loudnessAnalysisArtifact", {})
    )
    root = Path(str(artifact.get("absolutePath") or ""))
    if not artifact.get("artifactId") or not root.is_absolute():
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Track loudness requires carrier-owned PCM custody.",
        )
    root.parent.mkdir(parents=True, exist_ok=True)
    step = int(binding["stepIndex"])
    prefix = f"{root.stem}.track-{binding['trackIndex']}-step-{step:03d}"
    before_path = root.with_name(f"{prefix}-before.wav")
    before_control_path = root.with_name(f"{prefix}-before-control.wav")
    after_path = root.with_name(f"{prefix}-after.wav")
    after_control_path = root.with_name(f"{prefix}-after-control.wav")
    ffmpeg = audio_ops._ffmpeg_bin()
    original = _number(binding.get("originalFaderDb"), "bound track fader")
    if _read_fader(binding, flush=True) != original:
        raise FairlightEvaluationError(
            "STALE_REVISION", "Track fader changed after preparation."
        )
    applied = original
    try:
        before_control = _render_isolated(
            binding, before_control_path, ffmpeg=ffmpeg, target_enabled=False
        )
        before = _render_isolated(binding, before_path, ffmpeg=ffmpeg)
        verify_target_source(before, before_control)
        planned = plan_fader(before, original, request)
        if planned != original:
            if _read_fader(binding, flush=True) != original:
                raise FairlightEvaluationError(
                    "STALE_REVISION", "Track fader changed during loudness measurement."
                )
            applied = planned
            _set_fader(binding, applied)
        after = _render_isolated(binding, after_path, ffmpeg=ffmpeg)
        after_control = _render_isolated(
            binding, after_control_path, ffmpeg=ffmpeg, target_enabled=False
        )
        verify_target_source(after, after_control)
        verify_measurement(after, request)
        return {
            "before": before,
            "after": after,
            "sourceProof": {
                "status": "verified",
                "before": {
                    "targetPcmSha256": before["pcmSha256"],
                    "targetPeakSampleAbs": before["pcmPeakSampleAbs"],
                    "controlPcmSha256": before_control["pcmSha256"],
                    "controlPeakSampleAbs": before_control["pcmPeakSampleAbs"],
                },
                "after": {
                    "targetPcmSha256": after["pcmSha256"],
                    "targetPeakSampleAbs": after["pcmPeakSampleAbs"],
                    "controlPcmSha256": after_control["pcmSha256"],
                    "controlPeakSampleAbs": after_control["pcmPeakSampleAbs"],
                },
            },
            "originalFaderDb": original,
            "appliedFaderDb": applied,
            "trackIndex": binding["trackIndex"],
            "rangeDigest": binding["rangeDigest"],
        }
    except Exception:
        if applied != original:
            _restore_fader(binding, original, applied)
        raise
    finally:
        before_path.unlink(missing_ok=True)
        before_control_path.unlink(missing_ok=True)
        after_path.unlink(missing_ok=True)
        after_control_path.unlink(missing_ok=True)
