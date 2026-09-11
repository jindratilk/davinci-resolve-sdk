"""Public result projection for verified native clip audio and fade mutations."""
from copy import deepcopy
import math

from ..errors import ValidationError


def project_native_audio(action_id, prepared, after, data, verification):
    kind = {"cutagent.action.clip.audio_normalize": "audio_normalize", "cutagent.action.clip.audio_pan": "audio_pan", "cutagent.action.clip.audio_pitch": "audio_pitch", "cutagent.action.clip.fade_in": "fade"}[action_id]
    proof = data.get("verification", {})
    check_name = "native_clip_fades" if kind == "fade" else "native_clip_properties"
    if proof.get("status") != "verified" or not any(check.get("name") == check_name and check.get("ok") is True for check in proof.get("checks", []) if isinstance(check, dict)):
        raise ValidationError("Native clip audio result lacks exact API readback.")
    targets = after.get("preState", {}).get("publicTargets")
    if not isinstance(targets, list) or not targets:
        raise ValidationError("Native clip audio result lacks public targets.")
    if kind == "fade":
        rows = data.get("native_items")
        if not isinstance(rows, list) or len(rows) != len(targets):
            raise ValidationError("Native fade result does not cover its exact targets.")
        states = []
        # The command emits video then audio; stable labels keep private native IDs out of the result.
        track_types = [track for track in ("video", "audio") if data.get("scope") in {"linked", track}]
        if len(track_types) != len(rows):
            raise ValidationError("Native fade result has inconsistent scope.")
        for edge in ("before", "after"):
            states.append({f"{track}.{key}": row.get(edge, {}).get(key)
                           for track, row in zip(track_types, rows) for key in ("FadeIn", "FadeOut")})
    else:
        keys = {"audio_normalize": ("AudioVolume", "AudioVolumeEnabled"), "audio_pan": ("AudioPan", "AudioPanEnabled"), "audio_pitch": ("AudioPitchSemiTones", "AudioPitchCents", "AudioPitchEnabled")}[kind]
        if len(targets) != 1:
            raise ValidationError("Native audio result requires exactly one public target.")
        states = [{key: data.get(f"native_{edge}", {}).get(key) for key in keys} for edge in ("before", "after")]
    for state in states:
        for key, value in state.items():
            if key.endswith("Enabled"):
                valid = isinstance(value, bool)
            else:
                valid = not isinstance(value, bool) and isinstance(value, (float, int)) and math.isfinite(value)
                if kind == "fade":
                    valid = valid and value >= 0 and value == int(value)
            if not valid:
                raise ValidationError("Native clip audio result contains invalid numeric state.")
    before_revision = prepared.get("domain", {}).get("preState", {}).get("semanticState", {}).get("snapshotRevision")
    after_revision = after.get("preState", {}).get("semanticState", {}).get("snapshotRevision")
    changed = states[0] != states[1]
    if not isinstance(before_revision, str) or not isinstance(after_revision, str) or changed != (before_revision != after_revision):
        raise ValidationError("Native clip audio revision does not match observed state changes.")
    state_value = lambda state: {"kind": kind, "values": [{"name": key, "value": value} for key, value in sorted(state.items())]}
    return {"actionId": action_id, "payload": {
        "status": "completed" if changed else "no_change", "changed": changed,
        "revision": {"relationship": "advanced", "before": before_revision, "after": after_revision} if changed else {"relationship": "unchanged", "current": after_revision},
        "targets": deepcopy(targets), "change": {"kind": kind, "before": state_value(states[0]), "after": state_value(states[1])},
        "verification": verification,
        "recovery": {"state": "not_needed", "retry": "inspect_state_first", "guidance": "The exact clip controls were read back through the native API."},
    }}
