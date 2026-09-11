"""DaVinci Resolve 21.1 clip audio properties and faders, with exact readback."""
from __future__ import annotations

import math
from typing import Any

from ..errors import APICallFailed, SdkMutationStaleRevision, ValidationError
from ..output import set_execution_engine, set_recoverability, set_verification_status
from . import resolve_api_version, timeline_ops


def available(conn: Any, *, gain_db: float | None = None) -> bool:
    """Only older/unknown runtimes and the unsupported gain range use the legacy route."""
    if gain_db is not None and gain_db > 30.0:
        return False
    return resolve_api_version.at_least(conn, 21, 1)


def _item(conn: Any, ref: Any) -> Any:
    if not ref.item_id:
        raise ValidationError("Native clip mutation requires an exact timeline item identity.")
    matches = [item for item in conn.timeline.GetItemListInTrack(ref.track_type, ref.track_index) or []
               if str(item.GetUniqueId()) == ref.item_id]
    if len(matches) != 1 or int(matches[0].GetStart()) != ref.start or int(matches[0].GetEnd()) != ref.end:
        raise SdkMutationStaleRevision("The exact clip changed before its native audio mutation.")
    return matches[0]


def _read(item: Any, method: str, keys: tuple[str, ...], *, fades: bool = False) -> dict[str, Any]:
    getter = getattr(item, method, None)
    if not callable(getter):
        raise APICallFailed(f"DaVinci Resolve 21.1 requires TimelineItem.{method} for native clip readback.")
    values = getter()
    if not isinstance(values, dict):
        raise APICallFailed("Native clip readback did not return a property dictionary.")
    result = {}
    for key in keys:
        value = values.get(key)
        if key.endswith("Enabled"):
            if not isinstance(value, bool):
                raise APICallFailed("Native clip enabled-state readback is invalid.", details={"property": key})
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise APICallFailed("Native clip numeric readback is invalid.", details={"property": key})
        elif fades:
            if value < 0:
                raise APICallFailed("Native fade readback must be nonnegative.")
            # Audio faders can return subframe durations in real projects.
            # Preserve them for revision hashing and exact restoration.
            value = int(value) if value == int(value) else float(value)
        result[key] = value
    return result


def _matches(actual: dict, expected: dict) -> bool:
    return all(actual.get(key) is value if isinstance(value, bool)
               else isinstance(actual.get(key), (int, float)) and not isinstance(actual.get(key), bool)
               and math.isclose(actual[key], value, rel_tol=0.0, abs_tol=1e-6)
               for key, value in expected.items())


def _apply(conn: Any, plans: list[dict], *, fades: bool = False) -> list[dict]:
    getter, setter = ("GetFades", "SetFades") if fades else ("GetProperties", "SetProperties")
    for plan in plans:
        item = _item(conn, plan["ref"])
        if not callable(getattr(item, setter, None)):
            raise APICallFailed(f"DaVinci Resolve 21.1 requires TimelineItem.{setter}.")
        plan["before"] = _read(item, getter, tuple(plan["expected"]), fades=fades)
    attempted = []
    try:
        timeline_ops.require_sdk_marker_mutation_guard(conn)
        for plan in plans:
            item = _item(conn, plan["ref"])
            if not _matches(_read(item, getter, tuple(plan["before"]), fades=fades), plan["before"]):
                raise SdkMutationStaleRevision("Clip audio state changed after native preflight.")
            if not _matches(plan["before"], plan["expected"]):
                attempted.append(plan)
                if getattr(item, setter)(plan["write"]) is not True:
                    raise APICallFailed(f"TimelineItem.{setter} rejected the clip mutation.")
            plan["after"] = _read(item, getter, tuple(plan["expected"]), fades=fades)
            if not _matches(plan["after"], plan["expected"]):
                raise APICallFailed("Native clip audio readback did not match the requested values.")
    except Exception as exc:
        restored = True
        for plan in reversed(attempted):
            try:
                item = _item(conn, plan["ref"])
                restored = (getattr(item, setter)(plan["before"]) is True
                            and _matches(_read(item, getter, tuple(plan["before"]), fades=fades), plan["before"])) and restored
            except Exception:
                restored = False
        if not attempted:
            raise
        raise APICallFailed("Native clip audio mutation failed; inspect the reported restoration before retrying.",
                            details={"restoration_verified": restored, "attempted_items": len(attempted)}) from exc
    set_execution_engine("api_native")
    set_verification_status("verified")
    set_recoverability("not_applicable")
    return plans


def set_audio(conn: Any, ref: Any, *, kind: str, values: dict[str, float]) -> dict[str, Any]:
    enabled_key = {"audio-gain": "AudioVolumeEnabled", "audio-pan": "AudioPanEnabled", "audio-pitch": "AudioPitchEnabled"}[kind]
    before = _read(_item(conn, ref), "GetProperties", (*values, enabled_key))
    # Existing section activation is separate from changing its numeric controls.
    expected = {**values, enabled_key: before[enabled_key]}
    plan = _apply(conn, [{"ref": ref, "write": values, "expected": expected}])[0]
    data = {"effect": kind, "audio_item_id": ref.item_id,
            "native_before": plan["before"], "native_after": plan["after"],
            "verification": {"status": "verified", "checks": [{"name": "native_clip_properties", "ok": True}]}}
    if kind == "audio-gain":
        data.update(existing_gain_db=plan["before"]["AudioVolume"], resulting_gain_db=plan["after"]["AudioVolume"])
        data["verification"].update(actual_gain_db=plan["after"]["AudioVolume"], checks=[{"name": "exact_audio_gain_db", "ok": True}])
    return data


def set_fades(conn: Any, selection: dict, *, scope: str, edge: str,
              video_frames: int | None, audio_frames: int | None) -> dict[str, Any]:
    plans = []
    for track_type, frames in (("video", video_frames), ("audio", audio_frames)):
        if scope not in {"linked", track_type}:
            continue
        ref = selection.get(track_type)
        if ref is None:
            raise ValidationError("Fade requires an item for each requested track type.", details={"track_type": track_type})
        if isinstance(frames, bool) or not isinstance(frames, int) or frames < 1 or frames > ref.duration:
            raise ValidationError("Fade duration must fit the exact clip and contain at least one frame.")
        before = _read(_item(conn, ref), "GetFades", ("FadeIn", "FadeOut"), fades=True)
        write = {key: frames for key in ("FadeIn", "FadeOut") if edge == "both" or (key == "FadeIn") == (edge == "start")}
        plans.append({"ref": ref, "write": write, "expected": {**before, **write}})
    result = _apply(conn, plans, fades=True)
    return {"effect": "fade-in", "scope": scope, "edge": edge,
            "video_item_id": selection["video"].item_id if scope in {"linked", "video"} else None,
            "audio_item_id": selection["audio"].item_id if scope in {"linked", "audio"} else None,
            "video_duration_frames": video_frames, "audio_duration_frames": audio_frames,
            "native_items": [{"item_id": plan["ref"].item_id, "before": plan["before"], "after": plan["after"]} for plan in result],
            "verification": {"status": "verified", "checks": [{"name": "native_clip_fades", "ok": True}]}}


def enrich_inspector_revisions(conn: Any, rows: list[dict], items: list[Any], *, track_type: str) -> None:
    """Bind live 21.1 controls to SDK revisions, including controls outside packed DB effects."""
    if track_type not in {"video", "audio"} or not available(conn):
        return
    import hashlib
    import json
    for row, item in zip(rows, items):
        get_type = getattr(item, "GetType", None)
        if callable(get_type) and get_type() == "transition":
            continue
        fades = _read(item, "GetFades", ("FadeIn", "FadeOut"), fades=True)
        audio = _read(item, "GetProperties", ("AudioVolume", "AudioVolumeEnabled", "AudioPan", "AudioPanEnabled",
                     "AudioPitchSemiTones", "AudioPitchCents", "AudioPitchEnabled")) if track_type == "audio" else None
        state = {"persisted": row.get("inspector_state_digest"), "fades": fades, "audio": audio}
        row["inspector_state_digest"] = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def apply_batch_preview(conn: Any, preview: dict, *, property_key: str | None = None,
                        value: float | None = None, edge: str | None = None) -> dict:
    """Keep reviewed selector/planning semantics, execute without a DB write/reopen."""
    from .db_timeline_selection import LiveItemRef
    plans = []
    live = {}
    for index in range(1, int(conn.timeline.GetTrackCount('audio')) + 1):
        for item in conn.timeline.GetItemListInTrack('audio', index) or []:
            identity = str(item.GetUniqueId())
            if identity in live:
                raise ValidationError('Audio batch native identity is ambiguous.')
            live[identity] = (index, item)
    for row in preview['updated_items']:
        match = live.get(row['item_id'])
        if match is None:
            raise SdkMutationStaleRevision('Audio batch target is no longer present.')
        index, item = match
        ref = LiveItemRef('audio', index, item.GetName(), int(item.GetStart()),
                          int(item.GetEnd()) - int(item.GetStart()), item_id=row['item_id'])
        if edge is not None:
            before = _read(item, 'GetFades', ('FadeIn', 'FadeOut'), fades=True)
            if edge == 'crossfade':
                write = {}
                for row_key, native_key in (
                    ('fade_in_frames', 'FadeIn'),
                    ('fade_out_frames', 'FadeOut'),
                ):
                    if row.get(row_key) is None:
                        continue
                    frames = row[row_key]
                    if (
                        not isinstance(frames, int)
                        or isinstance(frames, bool)
                        or not 0 <= frames <= ref.duration
                    ):
                        raise ValidationError('Audio batch fade must fit the native clip.')
                    write[native_key] = frames
                if not write:
                    raise ValidationError('Audio crossfade batch item requires a fade edge.')
            else:
                key = 'FadeOut' if edge == 'end' else 'FadeIn'
                frames = row['fade_out_frames' if edge == 'end' else 'fade_in_frames']
                if not isinstance(frames, int) or isinstance(frames, bool) or not 0 <= frames <= ref.duration:
                    raise ValidationError('Audio batch fade must fit the native clip.')
                write = {key: frames}
        else:
            enabled = 'AudioVolumeEnabled' if property_key == 'AudioVolume' else 'AudioPanEnabled'
            before = _read(item, 'GetProperties', (property_key, enabled))
            if property_key == 'AudioVolume' and value is None:
                requested = row.get('resulting_gain_db')
            elif property_key == 'AudioPan' and value is None:
                requested = row.get('resulting_pan')
            else:
                requested = value
            if isinstance(requested, bool) or not isinstance(requested, (int, float)) or not math.isfinite(requested):
                raise ValidationError('Audio batch item requires a finite native property value.')
            write = {property_key: float(requested)}
        plans.append({'ref': ref, 'write': write, 'expected': {**before, **write}})
    applied = _apply(conn, plans, fades=edge is not None)
    rows = []
    for row, plan in zip(preview['updated_items'], applied):
        updated = dict(row, native_before=plan['before'], native_after=plan['after'])
        if property_key == 'AudioVolume':
            updated['previous_gain_db'] = plan['before']['AudioVolume']
        elif property_key == 'AudioPan':
            updated['previous_pan'] = plan['before']['AudioPan']
        rows.append(updated)
    return {**preview, 'dry_run': False, 'changed': any(not _matches(p['before'], p['after']) for p in applied),
            'updated_count': len(rows), 'updated_items': rows, 'route': 'api_native',
            'verification': {'status': 'verified', 'checks': [{'name': 'native_audio_batch', 'ok': True}]}}
