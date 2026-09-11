"""Native sample-peak normalization with exact clip gain readback."""
from __future__ import annotations

from ..errors import APICallFailed, CapabilityNegotiationFailed
from ..output import set_execution_engine, set_recoverability, set_verification_status
from . import audio_normalize, native_clip_audio, timeline_ops


def normalize_peak(conn, ref, target_dbfs):
    target = audio_normalize.validate_target_dbfs(target_dbfs)
    timeline = conn.timeline
    modes_fn = getattr(timeline, "GetNormalizeAudioModes", None)
    normalize = getattr(timeline, "NormalizeAudioLevel", None)
    modes = modes_fn() if callable(modes_fn) else None
    if not callable(normalize) or not isinstance(modes, list) or "Sample Peak Program" not in modes:
        raise CapabilityNegotiationFailed("Native sample-peak normalization is unavailable in this DaVinci Resolve runtime.")
    item = native_clip_audio._item(conn, ref)
    before = native_clip_audio._read(item, "GetProperties", ("AudioVolume", "AudioVolumeEnabled"))
    if not callable(getattr(item, "SetProperties", None)):
        raise APICallFailed("Native normalization requires clip gain restoration support.")
    timeline_ops.require_sdk_marker_mutation_guard(conn)
    attempted = False
    try:
        attempted = True
        if normalize([item], {"normalizationMode": "Sample Peak Program", "targetLevel": target}) is not True:
            raise APICallFailed("DaVinci Resolve rejected native sample-peak normalization.")
        after = native_clip_audio._read(native_clip_audio._item(conn, ref), "GetProperties", ("AudioVolume", "AudioVolumeEnabled"))
        if after["AudioVolumeEnabled"] != before["AudioVolumeEnabled"]:
            raise APICallFailed("Native normalization unexpectedly changed clip volume activation.")
    except Exception as exc:
        restored = False
        if attempted:
            try:
                restored = item.SetProperties(before) is True and native_clip_audio._read(item, "GetProperties", tuple(before)) == before
            except Exception:
                pass
        raise APICallFailed("Native audio normalization failed; inspect restoration before retrying.", details={"restoration_verified": restored}) from exc
    set_execution_engine("api_native")
    set_verification_status("verified")
    set_recoverability("not_applicable")
    return {"effect": "audio-normalize", "mode": "peak", "target_dbfs": target,
            "audio_item_id": ref.item_id, "native_before": before, "native_after": after,
            "existing_gain_db": before["AudioVolume"], "resulting_gain_db": after["AudioVolume"],
            "applied_gain_db": after["AudioVolume"] - before["AudioVolume"],
            "verification": {"status": "verified", "checks": [{"name": "native_clip_properties", "ok": True},
                {"name": "native_normalization_accepted", "ok": True}]}}
