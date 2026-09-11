"""Signed-host execution for the public aggregate Fairlight plan action.

The public SDK carries only semantic changes.  This module owns the private
lowering to reviewed CutAgent CLI handlers and projects one correlated result;
no handler name or command argument crosses the public operation boundary.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import threading
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

import click
from typer.models import ArgumentInfo, OptionInfo

from .fairlight_prepared_evaluation import (
    FairlightEvaluationError,
    FairlightEvaluationExecutionAuthority,
    _callback,
    _canonical,
    _impact,
    _targets,
)


ACTION_ID = "cutagent.action.sdk.fairlight.plan.apply"
_HANDLER_LOCK = threading.RLock()
_SUPPORTED_KINDS = frozenset(
    {"clip_gain", "clip_pan", "clip_fade", "clip_fade_curve", "track_mix", "effect", "loudness"}
)
_UNSUPPORTED_KIND_REASONS = MappingProxyType(
    {
        "routing": (
            "The Fairlight bus route verifies the default output but cannot mutate "
            "an exact track route."
        ),
        "eq": (
            "The Fairlight EQ route cannot yet write and read back the exact "
            "requested clip and closed band state."
        ),
        "dynamics": (
            "The Fairlight dynamics route is sequence-scoped and cannot prove "
            "an exact track target."
        ),
        "synchronization": (
            "The available sync route creates placements and cannot synchronize "
            "the exact existing clip set."
        ),
    }
)
_CAPABILITY_BY_HANDLER = MappingProxyType(
    {
        "audio_gain_batch": "fairlight.audio_gain_batch",
        "audio_pan_batch": "fairlight.audio_pan_batch",
        "_sdk_audio_pan_items": "fairlight.audio_pan_batch",
        "fade_in_batch": "fairlight.fade_in_batch",
        "fade_out_batch": "fairlight.fade_out_batch",
        "crossfade_batch": "fairlight.crossfade_batch",
        "fade_curve": "fairlight.fade_out_batch",
        "mixer_fader": "fairlight.fader",
        "mixer_pan": "fairlight.pan",
        "effect_add": "fairlight.clip_effect_param_write",
    }
)


def _sha(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _default(parameter: inspect.Parameter) -> Any:
    value = parameter.default
    if isinstance(value, (ArgumentInfo, OptionInfo)):
        value = value.default
    if value is inspect.Parameter.empty or value is ...:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR",
            f"Missing private Fairlight plan argument: {parameter.name}.",
        )
    return deepcopy(value)


def _invoke(handler_name: str, supplied: Mapping[str, Any]) -> Mapping[str, Any]:
    from .commands import fairlight as commands

    if handler_name == "crossfade_batch":
        if set(supplied) != {"entries", "clamp_half_clip"}:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR",
                "Private Fairlight crossfade lowering changed its contract.",
            )
        commands.enforce_mutation_policy(
            "fairlight.crossfade_batch",
            intended_engine="db_workaround",
            mutating=False,
        )
        result = commands.fairlight_ops.apply_audio_crossfade_batch(
            commands.get_connection(require_timeline=True),
            entries=deepcopy(supplied["entries"]),
            duration=None,
            clamp_half_clip=bool(supplied["clamp_half_clip"]),
            allow_empty=False,
        )
        if not isinstance(result, Mapping):
            raise FairlightEvaluationError(
                "API_CALL_FAILED", "Fairlight crossfade batch returned no structured result."
            )
        return _canonical(result)

    handler = getattr(commands, handler_name, None)
    if not callable(handler) or handler_name not in _CAPABILITY_BY_HANDLER:
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "A reviewed Fairlight plan route is unavailable.",
        )
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__
    signature = inspect.signature(handler)
    kwargs = {
        name: deepcopy(supplied[name]) if name in supplied else _default(parameter)
        for name, parameter in signature.parameters.items()
        if name != "ctx"
    }
    if set(supplied) - set(kwargs):
        raise FairlightEvaluationError(
            "VALIDATION_ERROR",
            "Private Fairlight plan lowering changed its handler contract.",
        )
    kwargs.update(deepcopy(dict(supplied)))
    captured: list[Any] = []
    with _HANDLER_LOCK:
        old_output = commands.output
        old_success = commands.success
        old_policy = commands.enforce_mutation_policy

        def admitted_policy(
            capability_id, *, intended_engine="api_native", mutating=True
        ):
            if (
                capability_id != ("fairlight.fade_in_batch" if handler_name == "fade_curve" and supplied.get("direction") == "in" else _CAPABILITY_BY_HANDLER[handler_name])
                or mutating is not True
            ):
                raise FairlightEvaluationError(
                    "CAPABILITY_NEGOTIATION_FAILED",
                    "A Fairlight plan step changed its admitted capability.",
                )
            return old_policy(
                capability_id, intended_engine=intended_engine, mutating=False
            )

        try:
            commands.output = lambda data, **_options: captured.append(deepcopy(data))
            commands.success = lambda message: captured.append(
                {"message": str(message)}
            )
            commands.enforce_mutation_policy = admitted_policy
            if "ctx" in signature.parameters:
                kwargs["ctx"] = click.Context(
                    click.Command(ACTION_ID), info_name=ACTION_ID
                )
            handler(**kwargs)
        finally:
            commands.output = old_output
            commands.success = old_success
            commands.enforce_mutation_policy = old_policy
    structured = [item for item in captured if isinstance(item, Mapping)]
    if not structured:
        raise FairlightEvaluationError(
            "API_CALL_FAILED", "A Fairlight plan step returned no structured result."
        )
    return _canonical(structured[0])


def _invoke_audio_gain_entries(entries: list[dict[str, Any]]) -> Mapping[str, Any]:
    """Execute one or many exact clip gains through one plural native operation."""
    if len(entries) == 1:
        entry = entries[0]
        return _invoke(
            "audio_gain_batch",
            {
                "db": entry["gain_db"],
                "item_ids": [entry["item_id"]],
                "allow_multiple": False,
            },
        )
    from .commands import fairlight as commands

    with _HANDLER_LOCK:
        commands.enforce_mutation_policy(
            _CAPABILITY_BY_HANDLER["audio_gain_batch"],
            intended_engine="db_workaround",
            mutating=False,
        )
        conn = commands.get_connection(require_timeline=True)
        result = commands.fairlight_ops.apply_audio_gain_entries(
            conn, entries=deepcopy(entries)
        )
    if not isinstance(result, Mapping):
        raise FairlightEvaluationError(
            "API_CALL_FAILED", "The Fairlight gain batch returned no structured result."
        )
    return _canonical(result)


def _invoke_fade_batch(
    handler_name: str, steps: list[Mapping[str, Any]]
) -> Mapping[str, Any]:
    """Invoke one existing plural fade command with per-item durations."""
    if handler_name not in {"fade_in_batch", "fade_out_batch"} or not steps:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "Private Fairlight fade batch lowering is invalid."
        )
    frame_key = "fade_in_frames" if handler_name == "fade_in_batch" else "fade_out_frames"
    entries: list[dict[str, Any]] = []
    for supplied in steps:
        item_ids = supplied.get("item_ids")
        duration = supplied.get("duration")
        if (
            not isinstance(item_ids, list)
            or len(item_ids) != 1
            or not isinstance(item_ids[0], str)
            or not item_ids[0]
            or not isinstance(duration, str)
            or not duration.endswith("f")
        ):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Private Fairlight fade batch entry is invalid."
            )
        try:
            frames = int(duration[:-1])
        except ValueError as exc:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Private Fairlight fade duration is invalid."
            ) from exc
        if frames <= 0:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Private Fairlight fade duration is invalid."
            )
        entries.append({"item_id": item_ids[0], frame_key: frames})

    from .commands import fairlight as commands

    apply = (
        commands.fairlight_ops.apply_audio_fade_in_batch
        if handler_name == "fade_in_batch"
        else commands.fairlight_ops.apply_audio_fade_out_batch
    )
    with _HANDLER_LOCK:
        commands.enforce_mutation_policy(
            _CAPABILITY_BY_HANDLER[handler_name],
            intended_engine="db_workaround",
            mutating=False,
        )
        result = apply(
            commands.get_connection(require_timeline=True),
            entries=entries,
            duration=None,
            skip_adjacent_same_track=False,
            clamp_half_clip=False,
            gain_db=None,
            allow_empty=False,
        )
    if not isinstance(result, Mapping):
        raise FairlightEvaluationError(
            "API_CALL_FAILED", "The Fairlight fade batch returned no structured result."
        )
    return _canonical(result)


def _validate_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "projectId",
        "timelineId",
        "timelineRevision",
        "changes",
        "preserveLinkedMedia",
    }:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "Fairlight plan input is not closed."
        )
    if value.get("preserveLinkedMedia") is not True:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "Fairlight plan safety policy changed."
        )
    changes = value.get("changes")
    if not isinstance(changes, list) or not 1 <= len(changes) <= 128:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "Fairlight plan step count is invalid."
        )
    binding = tuple(
        value.get(key) for key in ("projectId", "timelineId", "timelineRevision")
    )
    if any(not isinstance(item, str) or not item for item in binding):
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "Fairlight plan binding is incomplete."
        )
    for change in changes:
        if not isinstance(change, Mapping) or change.get("kind") not in {
            "clip_gain",
            "clip_pan",
            "clip_fade",
            "clip_fade_curve",
            "track_mix",
            "routing",
            "eq",
            "dynamics",
            "effect",
            "synchronization",
            "loudness",
        }:
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Fairlight plan change is invalid."
            )
        if (
            tuple(
                change.get(key)
                for key in ("projectId", "timelineId", "timelineRevision")
            )
            != binding
        ):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Fairlight plan step binding drifted."
            )
        if not isinstance(change.get("target"), Mapping):
            raise FairlightEvaluationError(
                "VALIDATION_ERROR", "Fairlight plan target is invalid."
            )
    return _canonical(value)


def _semantic_target_keys(plan: Mapping[str, Any]) -> list[tuple[str, Any]]:
    keys: list[tuple[str, Any]] = []
    seen: set[tuple[str, Any]] = set()
    for change in plan["changes"]:
        target = change["target"]
        rows = target["clips"] if target.get("kind") == "clips" else [target]
        for row in rows:
            if row.get("kind") == "clip" or "clipId" in row:
                key = ("clip", row["clipId"])
            elif row.get("kind") == "track":
                key = ("track", row["trackIndex"])
            elif row.get("kind") == "bus":
                key = ("timeline", plan["timelineId"])
            else:
                raise FairlightEvaluationError(
                    "VALIDATION_ERROR", "Fairlight plan target is unsupported."
                )
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def _target_kinds(plan: Mapping[str, Any]) -> list[str]:
    return [kind for kind, _identity in _semantic_target_keys(plan)]


def _locator_by_key(
    plan: Mapping[str, Any], resolved: list[Mapping[str, Any]]
) -> dict[tuple[str, Any], Mapping[str, Any]]:
    keys = _semantic_target_keys(plan)
    if len(keys) != len(resolved):
        raise FairlightEvaluationError(
            "STALE_REVISION", "Fairlight plan target closure changed."
        )
    return dict(zip(keys, resolved, strict=True))


def _verified_handler(value: Mapping[str, Any]) -> bool:
    verification = value.get("verification")
    return (
        isinstance(verification, Mapping)
        and verification.get("status") == "verified"
        and isinstance(verification.get("checks"), list)
        and all(
            isinstance(check, Mapping) and check.get("ok") is True
            for check in verification["checks"]
        )
    )


def _resolved_effect_spec(change: Mapping[str, Any]) -> Mapping[str, Any]:
    if change.get("presetId") is not None:
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Fairlight effect presets lack exact native preset proof.",
        )
    from .commands import fairlight as commands

    effect_spec = commands._resolve_fairlight_clip_fx_effect(change["pluginId"])
    if not isinstance(effect_spec, Mapping) or effect_spec.get("key") == "voice_isolation":
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "The requested Fairlight effect lacks exact Clip FX write/readback proof.",
        )
    return effect_spec


def _step_lowering(
    change: Mapping[str, Any],
    locators: Mapping[tuple[str, Any], Mapping[str, Any]],
    *,
    before_readback: Any,
) -> list[tuple[str, dict[str, Any]]]:
    kind = change["kind"]
    if kind not in _SUPPORTED_KINDS:
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            _UNSUPPORTED_KIND_REASONS.get(
                kind,
                f"The {kind} Fairlight plan route lacks exact target-scoped mutation proof.",
            ),
        )
    target = change["target"]
    if target["kind"] == "clip":
        locator = locators[("clip", target["clipId"])]
    elif target["kind"] == "track":
        locator = locators[("track", target["trackIndex"])]
    else:
        locator = locators[("timeline", change["timelineId"])]
    if kind == "clip_gain":
        return [
            (
                "audio_gain_batch",
                {
                    "db": change["gainDb"],
                    "item_ids": [locator["nativeId"]],
                    "allow_multiple": False,
                },
            )
        ]
    if kind == "clip_pan":
        current_pan = _readback_value(before_readback, change, locator)
        if (
            isinstance(current_pan, (int, float))
            and not isinstance(current_pan, bool)
            and math.isclose(float(current_pan), float(change["pan"]), abs_tol=1e-9)
        ):
            return []
        return [
            (
                "audio_pan_batch",
                {
                    "value": change["pan"] * 100.0,
                    "item_ids": [locator["nativeId"]],
                    "allow_multiple": False,
                },
            )
        ]
    if kind == "clip_fade_curve":
        point = change["curve"]["controlPoint"]
        return [("fade_curve", {"item_id": locator["nativeId"], "direction": change["direction"],
            "linear": point is None, "x": None if point is None else point["x"], "y": None if point is None else point["y"]})]
    if kind == "clip_fade":
        handler = "fade_in_batch" if change["direction"] == "in" else "fade_out_batch"
        adjacent = "skip_adjacent_same_track"
        return [
            (
                handler,
                {
                    "duration": f"{change['durationFrames']}f",
                    "item_ids": [locator["nativeId"]],
                    adjacent: False,
                    "clamp_half_clip": False,
                },
            )
        ]
    if kind == "track_mix":
        matches = [
            row
            for row in (before_readback.get("tracks") or [])
            if isinstance(row, Mapping)
            and row.get("trackIndex") == locator.get("trackIndex")
        ] if isinstance(before_readback, Mapping) else []
        baseline = matches[0] if len(matches) == 1 else None
        level = baseline.get("levelDb") if isinstance(baseline, Mapping) else None
        pan = baseline.get("pan") if isinstance(baseline, Mapping) else None
        pan_writable = (
            baseline.get("panWritable") if isinstance(baseline, Mapping) else None
        )
        if (
            not isinstance(level, (int, float))
            or isinstance(level, bool)
            or not math.isfinite(level)
            or not isinstance(pan, (int, float))
            or isinstance(pan, bool)
            or not math.isfinite(pan)
        ):
            raise FairlightEvaluationError(
                "CAPABILITY_NEGOTIATION_FAILED",
                "The requested Fairlight track mix lacks writable fader and pan readback.",
            )
        if pan_writable is False:
            if not math.isclose(float(change["pan"]), float(pan), abs_tol=1e-9):
                raise FairlightEvaluationError(
                    "CAPABILITY_NEGOTIATION_FAILED",
                    "The requested Fairlight track pan is not writable for this track format.",
                )
            return [
                (
                    "mixer_fader",
                    {"track": locator["trackIndex"], "level_db": change["levelDb"]},
                )
            ]
        return [
            (
                "mixer_fader",
                {"track": locator["trackIndex"], "level_db": change["levelDb"]},
            ),
            (
                "mixer_pan",
                {"track": locator["trackIndex"], "pan": change["pan"] * 100.0},
            ),
        ]
    if kind == "loudness":
        if target.get("kind") != "track":
            if target.get("kind") != "bus":
                raise FairlightEvaluationError(
                    "CAPABILITY_NEGOTIATION_FAILED",
                    "The Fairlight loudness plan route lacks exact target-scoped mutation proof.",
                )
            raise FairlightEvaluationError(
                "CAPABILITY_NEGOTIATION_FAILED",
                "Main-output loudness requires its separate exact output-identity route.",
            )
        return []
    if kind == "routing":
        return [
            (
                "bus_assign",
                {
                    "bus": change["destination"]["busName"],
                    "track": locator["trackIndex"],
                },
            )
        ]
    if kind != "effect":
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            f"The {kind} Fairlight plan route lacks exact target-scoped mutation proof.",
        )
    effect_spec = _resolved_effect_spec(change)
    if not isinstance(before_readback, Mapping) or before_readback.get("status") != "available":
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "The requested Fairlight effect lacks fresh Clip FX pre-state.",
        )
    matches = [
        row
        for row in before_readback.get("clips") or []
        if isinstance(row, Mapping)
        and row.get("nativeId") == locator.get("nativeId")
        and row.get("stableId") == locator.get("stableId")
    ]
    plugin_ids = matches[0].get("effectPluginIds") if len(matches) == 1 else None
    if not isinstance(plugin_ids, list):
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "The requested Fairlight effect lacks fresh Clip FX pre-state.",
        )
    if effect_spec["plugin_id"] in plugin_ids:
        return []
    if plugin_ids:
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Adding to an existing Fairlight multi-plugin stack lacks preservation proof.",
        )
    return [
        (
            "effect_add",
            {
                "effect": effect_spec["plugin_id"],
                "clip": locator["nativeId"],
            },
        )
    ]


def _plan_lowerings(
    plan: Mapping[str, Any],
    locators: Mapping[tuple[str, Any], Mapping[str, Any]],
    *,
    before_readback: Any,
) -> list[list[tuple[str, dict[str, Any]]]]:
    lowerings: list[list[tuple[str, dict[str, Any]]]] = []
    effect_by_clip: dict[str, str] = {}
    for change in plan["changes"]:
        if change["kind"] == "effect":
            clip_id = change["target"]["clipId"]
            plugin_id = str(_resolved_effect_spec(change)["plugin_id"])
            previous = effect_by_clip.get(clip_id)
            if previous is not None and previous != plugin_id:
                raise FairlightEvaluationError(
                    "CAPABILITY_NEGOTIATION_FAILED",
                    "Distinct Fairlight effects on one clip require unproven "
                    "multi-plugin stack preservation.",
                )
            if previous == plugin_id:
                lowerings.append([])
                continue
            effect_by_clip[clip_id] = plugin_id
        lowerings.append(
            _step_lowering(
                change,
                locators,
                before_readback=before_readback,
            )
        )

    crossfade_groups: list[tuple[int, int, Mapping[str, Any], Mapping[str, Any]]] = []
    index = 0
    while index + 1 < len(plan["changes"]):
        outgoing = plan["changes"][index]
        incoming = plan["changes"][index + 1]
        if (
            outgoing.get("kind") == "clip_fade"
            and outgoing.get("direction") == "out"
            and incoming.get("kind") == "clip_fade"
            and incoming.get("direction") == "in"
            and outgoing.get("durationFrames") == incoming.get("durationFrames")
        ):
            outgoing_locator = locators[("clip", outgoing["target"]["clipId"])]
            incoming_locator = locators[("clip", incoming["target"]["clipId"])]
            if (
                outgoing_locator.get("trackIndex") == incoming_locator.get("trackIndex")
                and outgoing_locator.get("recordEndFrameExclusive") == incoming_locator.get("recordStartFrame")
            ):
                crossfade_groups.append((index, index + 1, outgoing, incoming))
                index += 2
                continue
        index += 1
    group_start = 0
    while group_start < len(crossfade_groups):
        group_end = group_start + 1
        while (
            group_end < len(crossfade_groups)
            and crossfade_groups[group_end][0]
            == crossfade_groups[group_end - 1][1] + 1
        ):
            group_end += 1
        contiguous_pairs = crossfade_groups[group_start:group_end]
        entries = [
            {
                "left_item_id": locators[("clip", outgoing["target"]["clipId"])]["nativeId"],
                "right_item_id": locators[("clip", incoming["target"]["clipId"])]["nativeId"],
                "fade_duration_frames": outgoing["durationFrames"],
            }
            for _outgoing_index, _incoming_index, outgoing, incoming in contiguous_pairs
        ]
        shared = (
            "crossfade_batch",
            {"entries": entries, "clamp_half_clip": False},
        )
        for outgoing_index, incoming_index, _outgoing, _incoming in contiguous_pairs:
            lowerings[outgoing_index] = [shared]
            lowerings[incoming_index] = [shared]
        group_start = group_end
    return lowerings


def _track_loudness_bindings(
    context: Mapping[str, Any],
    plan: Mapping[str, Any],
    response: Mapping[str, Any],
    locators: Mapping[tuple[str, Any], Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    """Close every track-loudness request over one exact occupied range."""
    loudness = [
        (index, change)
        for index, change in enumerate(plan["changes"])
        if change["kind"] == "loudness"
    ]
    if not loudness:
        return {}
    targets = [change["target"] for _, change in loudness]
    if any(target.get("kind") != "track" for target in targets):
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Main-output loudness requires its separate exact output-identity route.",
        )
    indexes = [target["trackIndex"] for target in targets]
    if len(indexes) != len(set(indexes)):
        raise FairlightEvaluationError(
            "VALIDATION_ERROR", "A Fairlight plan may normalize each exact track once."
        )
    conflicting_mix = {
        change["target"]["trackIndex"]
        for change in plan["changes"]
        if change["kind"] == "track_mix" and change["target"].get("kind") == "track"
    } & set(indexes)
    if conflicting_mix:
        raise FairlightEvaluationError(
            "VALIDATION_ERROR",
            "Track mix and loudness cannot both own the final fader of one track.",
        )
    snapshot = response.get("snapshot")
    audio_ranges = snapshot.get("audioRanges") if isinstance(snapshot, Mapping) else None
    overrides = response.get("handlerOverrides")
    closures = overrides.get("trackLoudness") if isinstance(overrides, Mapping) else None
    frame_rate = snapshot.get("frameRate") if isinstance(snapshot, Mapping) else None
    private = context.get("privateBindings")
    fairlight = private.get("fairlight") if isinstance(private, Mapping) else None
    native_project_id = fairlight.get("nativeProjectId") if isinstance(fairlight, Mapping) else None
    native_timeline_id = fairlight.get("nativeTimelineId") if isinstance(fairlight, Mapping) else None
    if (
        not isinstance(closures, list)
        or len(closures) != len(loudness)
        or not isinstance(frame_rate, Mapping)
        or not isinstance(frame_rate.get("numerator"), int)
        or not isinstance(frame_rate.get("denominator"), int)
        or frame_rate["numerator"] <= 0
        or frame_rate["denominator"] <= 0
        or not isinstance(native_project_id, str)
        or not native_project_id
        or not isinstance(native_timeline_id, str)
        or not native_timeline_id
    ):
        raise FairlightEvaluationError(
            "CAPABILITY_NEGOTIATION_FAILED",
            "Track loudness lacks exact range, rate, or native timeline custody.",
        )
    result: dict[str, Mapping[str, Any]] = {}
    for (step_index, change), closure in zip(loudness, closures, strict=True):
        target_index = change["target"]["trackIndex"]
        locator = locators.get(("track", target_index))
        track_readbacks = (
            snapshot.get("actionReadback", {}).get("tracks", [])
            if isinstance(snapshot, Mapping)
            else []
        )
        matching_readbacks = [
            row
            for row in track_readbacks
            if isinstance(row, Mapping) and row.get("trackIndex") == target_index
        ]
        current_fader = (
            closure.get("currentFaderDb") if isinstance(closure, Mapping) else None
        )
        if (
            not isinstance(closure, Mapping)
            or closure.get("trackIndex") != target_index
            or not isinstance(closure.get("startFrame"), int)
            or not isinstance(closure.get("endExclusiveFrame"), int)
            or closure["endExclusiveFrame"] <= closure["startFrame"]
            or not isinstance(closure.get("clipIds"), list)
            or not closure["clipIds"]
            or len(closure["clipIds"]) != len(set(closure["clipIds"]))
            or not isinstance(closure.get("rangeDigest"), str)
            or not closure["rangeDigest"].startswith("sha256:")
            or not isinstance(current_fader, (int, float))
            or isinstance(current_fader, bool)
            or not math.isfinite(current_fader)
            or len(matching_readbacks) != 1
            or matching_readbacks[0].get("levelDb") != current_fader
            or not isinstance(locator, Mapping)
            or locator.get("trackIndex") != target_index
        ):
            raise FairlightEvaluationError(
                "CAPABILITY_NEGOTIATION_FAILED",
                "Track loudness target closure is incomplete or ambiguous.",
            )
        ranges = sorted(
            (
                {
                    "clipId": row.get("clipId"),
                    "startFrame": row.get("startFrame"),
                    "endExclusiveFrame": row.get("endExclusiveFrame"),
                }
                for row in audio_ranges or []
                if isinstance(row, Mapping) and row.get("trackIndex") == target_index
            ),
            key=lambda row: (
                row["startFrame"] if isinstance(row["startFrame"], int) else -1,
                row["endExclusiveFrame"] if isinstance(row["endExclusiveFrame"], int) else -1,
                row["clipId"] if isinstance(row["clipId"], str) else "",
            ),
        )
        if (
            not ranges
            or any(
                not isinstance(row["clipId"], str)
                or not row["clipId"]
                or not isinstance(row["startFrame"], int)
                or not isinstance(row["endExclusiveFrame"], int)
                or row["endExclusiveFrame"] <= row["startFrame"]
                for row in ranges
            )
            or [row["clipId"] for row in ranges] != closure["clipIds"]
            or min(row["startFrame"] for row in ranges) != closure["startFrame"]
            or max(row["endExclusiveFrame"] for row in ranges)
            != closure["endExclusiveFrame"]
            or _sha({"trackIndex": target_index, "ranges": ranges})
            != closure["rangeDigest"]
        ):
            raise FairlightEvaluationError(
                "CAPABILITY_NEGOTIATION_FAILED",
                "Track loudness range closure does not match the exact live snapshot.",
            )
        result[str(step_index)] = _canonical(
            {
                "stepIndex": step_index,
                "trackIndex": target_index,
                "nativeProjectId": native_project_id,
                "nativeTimelineId": native_timeline_id,
                "originalFaderDb": current_fader,
                "startFrame": closure["startFrame"],
                "endExclusiveFrame": closure["endExclusiveFrame"],
                "clipIds": closure["clipIds"],
                "rangeDigest": closure["rangeDigest"],
                "frameRate": {
                    "numerator": frame_rate["numerator"],
                    "denominator": frame_rate["denominator"],
                },
            }
        )
    return result


def _loudness_structural_binding(binding: Mapping[str, Any]) -> Mapping[str, Any]:
    return _canonical(
        {key: value for key, value in binding.items() if key != "originalFaderDb"}
    )


def _one_updated(result: Mapping[str, Any], native_id: str) -> Mapping[str, Any]:
    rows = result.get("updated_items")
    matches = [
        row
        for row in rows or []
        if isinstance(row, Mapping) and row.get("item_id") == native_id
    ]
    if len(matches) != 1 or not _verified_handler(result):
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Fairlight plan DB readback is incomplete."
        )
    return matches[0]


def _readback_value(
    readback: Any, change: Mapping[str, Any], locator: Mapping[str, Any]
) -> Any:
    if not isinstance(readback, Mapping) or readback.get("status") != "available":
        raise FairlightEvaluationError(
            "VERIFICATION_FAILED", "Fresh Fairlight plan readback is unavailable."
        )
    kind = change["kind"]
    if kind in {"clip_gain", "clip_pan", "clip_fade", "clip_fade_curve"}:
        rows = readback.get("clips")
        matches = [
            row
            for row in rows or []
            if isinstance(row, Mapping)
            and row.get("nativeId") == locator.get("nativeId")
            and row.get("stableId") == locator.get("stableId")
        ]
        if len(matches) != 1:
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fresh Fairlight clip readback is incomplete."
            )
        row = matches[0]
        if kind == "clip_gain":
            # Native clips without an explicit gain entry have unity gain,
            # matching clip_effects_db.read_current_audio_gain.
            return 0.0 if "gainDb" in row and row["gainDb"] is None else row.get("gainDb")
        if kind == "clip_pan":
            value = row.get("pan")
            if value is None:
                return 0.0
            return (
                value / 100.0
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else None
            )
        if kind == "clip_fade_curve":
            value = row.get("fadeInCurve" if change["direction"] == "in" else "fadeOutCurve")
            if not isinstance(value, Mapping) or "controlPoint" not in value:
                raise FairlightEvaluationError("VERIFICATION_FAILED", "Fresh fade curve readback is unavailable.")
            return dict(value)
        field = "fadeInFrames" if change["direction"] == "in" else "fadeOutFrames"
        # An explicit native null means no fade envelope: zero frames. A
        # missing field remains unavailable, just like the gain baseline.
        return 0 if field in row and row[field] is None else row.get(field)
    if kind == "track_mix":
        rows = readback.get("tracks")
        matches = [
            row
            for row in rows or []
            if isinstance(row, Mapping)
            and row.get("trackIndex") == locator.get("trackIndex")
        ]
        if len(matches) != 1:
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED",
                "Fresh Fairlight track-mix readback is incomplete.",
            )
        row = matches[0]
        level = row.get("levelDb")
        pan = row.get("pan")
        if (
            not isinstance(level, (int, float))
            or isinstance(level, bool)
            or not isinstance(pan, (int, float))
            or isinstance(pan, bool)
        ):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED",
                "Fresh Fairlight track-mix readback is incomplete.",
            )
        return {"levelDb": level, "pan": pan}
    if kind == "effect":
        rows = readback.get("clips")
        matches = [
            row
            for row in rows or []
            if isinstance(row, Mapping)
            and row.get("nativeId") == locator.get("nativeId")
            and row.get("stableId") == locator.get("stableId")
        ]
        if len(matches) != 1 or not isinstance(
            matches[0].get("effectPluginIds"), list
        ):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED",
                "Fresh Fairlight clip-effect readback is incomplete.",
            )
        from .commands import fairlight as commands

        effect_spec = commands._resolve_fairlight_clip_fx_effect(change["pluginId"])
        if not isinstance(effect_spec, Mapping):
            raise FairlightEvaluationError(
                "CAPABILITY_NEGOTIATION_FAILED",
                "The requested Fairlight effect lacks exact Clip FX readback proof.",
            )
        return effect_spec["plugin_id"] in matches[0]["effectPluginIds"]
    raise FairlightEvaluationError(
        "CAPABILITY_NEGOTIATION_FAILED",
        "Fairlight plan semantic readback is unavailable.",
    )


def _semantic_change(
    change: Mapping[str, Any],
    results: list[Mapping[str, Any]],
    locator: Mapping[str, Any],
    *,
    before_readback: Any,
    current_readback: Any,
) -> dict[str, Any]:
    kind = change["kind"]
    if kind == "loudness":
        from .core import fairlight_track_loudness

        if len(results) != 1 or not isinstance(results[0], Mapping):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Track loudness receipt is incomplete."
            )
        receipt = results[0]
        if receipt.get("trackIndex") != change["target"].get("trackIndex"):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Track loudness receipt changed target."
            )
        fairlight_track_loudness.verify_measurement(receipt.get("after") or {}, change)
        return {
            "kind": "loudness",
            "before": {
                key: receipt["before"][key]
                for key in ("integratedLufs", "truePeakDbtp")
            },
            "after": {
                key: receipt["after"][key]
                for key in ("integratedLufs", "truePeakDbtp")
            },
        }
    before = _readback_value(before_readback, change, locator)
    after = _readback_value(current_readback, change, locator)
    if kind == "clip_gain":
        if not isinstance(before, (int, float)) or isinstance(before, bool):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fresh Fairlight gain baseline is unavailable."
            )
        _one_updated(results[0], locator["nativeId"])
        return {"kind": kind, "beforeDb": before, "afterDb": after}
    if kind == "clip_pan":
        if not isinstance(before, (int, float)) or isinstance(before, bool):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fresh Fairlight pan baseline is unavailable."
            )
        if not results:
            if (
                not isinstance(after, (int, float))
                or isinstance(after, bool)
                or not math.isclose(float(before), float(after), abs_tol=1e-9)
            ):
                raise FairlightEvaluationError(
                    "VERIFICATION_FAILED",
                    "No-op Fairlight pan readback changed unexpectedly.",
                )
        elif len(results) == 1:
            _one_updated(results[0], locator["nativeId"])
        else:
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fairlight pan receipt is incomplete."
            )
        return {"kind": kind, "before": before, "after": after}
    if kind == "clip_fade_curve":
        if len(results) != 1 or not _verified_handler(results[0]):
            raise FairlightEvaluationError("VERIFICATION_FAILED", "Fade curve receipt is incomplete.")
        return {"kind": kind, "direction": change["direction"], "before": before, "after": after}
    if kind == "clip_fade":
        if not isinstance(before, (int, float)) or isinstance(before, bool) or not math.isfinite(before) or before < 0:
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fresh Fairlight fade baseline is unavailable."
            )
        _one_updated(results[0], locator["nativeId"])
        edge = change["direction"]
        return {
            "kind": kind,
            "direction": edge,
            "beforeFrames": before,
            "afterFrames": after,
        }
    if kind == "track_mix":
        if not 1 <= len(results) <= 2 or any(
            not _verified_handler(result) for result in results
        ):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fairlight mixer readback is incomplete."
            )
        return {"kind": kind, "before": before, "after": after}
    if kind == "effect":
        if results and not _verified_handler(results[0]):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fairlight clip-effect readback is incomplete."
            )
        return {
            "kind": kind,
            "pluginId": change["pluginId"],
            "presetId": change.get("presetId"),
            "beforePresent": before,
            "afterPresent": after,
        }
    raise FairlightEvaluationError(
        "CAPABILITY_NEGOTIATION_FAILED",
        "Fairlight plan semantic projection is unavailable.",
    )


@dataclass(frozen=True)
class FairlightPlanPreparedActionDescriptor:
    authority: FairlightEvaluationExecutionAuthority

    operation_class = "mutation"
    version = 1
    capability_id = "sdk.fairlight.plan.apply"
    action_id = ACTION_ID

    def validate_input(self, value: Any) -> dict[str, Any]:
        return _validate_plan(value)

    def prepare(
        self, context: Mapping[str, Any], value: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        kinds = _target_kinds(value)
        response = _callback(
            self.authority,
            context,
            ACTION_ID,
            "prepare",
            {"normalizedInput": value},
            target_kinds=kinds,
        )
        targets = _targets(context, response)
        snapshot = response.get("snapshot")
        protected = response.get("protectedState")
        if (
            not isinstance(snapshot, Mapping)
            or not isinstance(protected, Mapping)
            or not isinstance(snapshot.get("audioRanges"), list)
            or not snapshot["audioRanges"]
            or not isinstance(snapshot.get("actionReadback"), Mapping)
            or snapshot["actionReadback"].get("status") != "available"
        ):
            raise FairlightEvaluationError(
                "CAPABILITY_NEGOTIATION_FAILED",
                "Fairlight plan independent readback is unavailable.",
            )
        locators = _locator_by_key(value, response["targets"])
        lowerings = _plan_lowerings(
            value,
            locators,
            before_readback=snapshot["actionReadback"],
        )
        loudness_bindings = _track_loudness_bindings(
            context, value, response, locators
        )
        impact = _impact(context, self, targets, audition_required=False)
        return {
            "targets": targets,
            "preState": {
                "snapshot": _canonical(snapshot),
                "protectedState": _canonical(protected),
            },
            "impact": _canonical(impact),
            "lowering": {
                "normalizedInput": _canonical(value),
                "steps": _canonical(lowerings),
                "trackLoudness": _canonical(loudness_bindings),
                "carrierAdmission": {
                    "actionId": ACTION_ID,
                    "executionId": context.get("executionId"),
                },
            },
            "verification": {
                "minimumEvidence": ["readback", "structural"]
            },
            "recovery": {"strategy": "live_audit_then_manual_recovery"},
        }

    def resolve_current(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        plan = prepared["lowering"]["normalizedInput"]
        response = _callback(
            self.authority,
            context,
            ACTION_ID,
            "current",
            {"preparedTargets": prepared["targets"]},
            target_kinds=_target_kinds(plan),
        )
        return {
            "targets": _targets(context, response),
            "preState": {
                "snapshot": _canonical(response["snapshot"]),
                "protectedState": _canonical(response["protectedState"]),
            },
        }

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        if context.get("executionAuthority") is not self.authority:
            raise FairlightEvaluationError(
                "AUTH_REQUIRED", "Fairlight plan authority changed."
            )
        admission = prepared.get("lowering", {}).get("carrierAdmission")
        if admission != {
            "actionId": ACTION_ID,
            "executionId": context.get("executionId"),
        }:
            raise FairlightEvaluationError(
                "AUTH_REQUIRED", "Fairlight plan admission changed."
            )
        plan = prepared["lowering"]["normalizedInput"]
        step_results: list[list[Mapping[str, Any]] | None] = [
            None for _change in plan["changes"]
        ]
        # Loudness proves final audio, so all other authored changes execute first.
        # This prevents a later fade/gain in the same aggregate plan from
        # invalidating the measured LUFS result.
        index = 0
        while index < len(plan["changes"]):
            change = plan["changes"][index]
            if change["kind"] == "loudness":
                index += 1
                continue
            if change["kind"] == "clip_gain":
                gain_entries: list[dict[str, Any]] = []
                gain_indices: list[int] = []
                next_index = index
                while (
                    next_index < len(plan["changes"])
                    and plan["changes"][next_index]["kind"] == "clip_gain"
                ):
                    kwargs = prepared["lowering"]["steps"][next_index][0][1]
                    gain_entries.append(
                        {
                            "item_id": kwargs["item_ids"][0],
                            "gain_db": plan["changes"][next_index]["gainDb"],
                        }
                    )
                    gain_indices.append(next_index)
                    next_index += 1
                gain_result = _invoke_audio_gain_entries(gain_entries)
                for gain_index in gain_indices:
                    step_results[gain_index] = [gain_result]
                index = next_index
                continue
            if change["kind"] != "clip_pan":
                step = prepared["lowering"]["steps"][index]
                if len(step) == 1 and step[0][0] == "crossfade_batch":
                    end = index + 1
                    while (
                        end < len(plan["changes"])
                        and prepared["lowering"]["steps"][end] == step
                    ):
                        end += 1
                    receipt = _invoke(*step[0])
                    for position in range(index, end):
                        step_results[position] = [receipt]
                    index = end
                    continue
                if (
                    change["kind"] == "clip_fade"
                    and len(step) == 1
                    and step[0][0] in {"fade_in_batch", "fade_out_batch"}
                ):
                    handler = step[0][0]
                    end = index + 1
                    while end < len(plan["changes"]):
                        candidate_change = plan["changes"][end]
                        candidate_step = prepared["lowering"]["steps"][end]
                        if (
                            candidate_change["kind"] != "clip_fade"
                            or len(candidate_step) != 1
                            or candidate_step[0][0] != handler
                        ):
                            break
                        end += 1
                    if end - index > 1:
                        batch_result = _invoke_fade_batch(
                            handler,
                            [
                                prepared["lowering"]["steps"][position][0][1]
                                for position in range(index, end)
                            ],
                        )
                        for position in range(index, end):
                            step_results[position] = [batch_result]
                        index = end
                        continue
                step_results[index] = [
                    _invoke(handler, kwargs) for handler, kwargs in step
                ]
                index += 1
                continue

            pan_items: list[dict[str, Any]] = []
            pan_indices: list[int] = []
            next_index = index
            while (
                next_index < len(plan["changes"])
                and plan["changes"][next_index]["kind"] == "clip_pan"
            ):
                step = prepared["lowering"]["steps"][next_index]
                if not step:
                    step_results[next_index] = []
                    next_index += 1
                    continue
                if len(step) != 1 or step[0][0] != "audio_pan_batch":
                    raise FairlightEvaluationError(
                        "CAPABILITY_NEGOTIATION_FAILED",
                        "Fairlight pan lowering changed its reviewed plural route.",
                    )
                kwargs = step[0][1]
                item_ids = kwargs.get("item_ids")
                if (
                    not isinstance(item_ids, list)
                    or len(item_ids) != 1
                    or not isinstance(item_ids[0], str)
                    or not item_ids[0]
                ):
                    raise FairlightEvaluationError(
                        "VALIDATION_ERROR", "Fairlight pan target identity is invalid."
                    )
                pan_items.append(
                    {"item_id": item_ids[0], "value": kwargs.get("value")}
                )
                pan_indices.append(next_index)
                next_index += 1
            if pan_items:
                pan_result = _invoke(
                    "_sdk_audio_pan_items",
                    {"items": pan_items[0] if len(pan_items) == 1 else pan_items},
                )
                for pan_index in pan_indices:
                    step_results[pan_index] = [pan_result]
            index = next_index
        from .core import fairlight_track_loudness

        for index, change in enumerate(plan["changes"]):
            if change["kind"] == "loudness":
                binding = prepared["lowering"]["trackLoudness"].get(str(index))
                if not isinstance(binding, Mapping):
                    raise FairlightEvaluationError(
                        "STALE_REVISION",
                        "Track loudness binding changed after preparation.",
                    )
                step_results[index] = [
                    fairlight_track_loudness.execute(context, binding, change)
                ]
        if any(result is None for result in step_results):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fairlight plan execution is incomplete."
            )
        response = _callback(
            self.authority,
            context,
            ACTION_ID,
            "verify",
            {
                "prepared": prepared,
                "handlerResult": {"stepResults": step_results},
                "protectedState": prepared.get("preState", {}).get("protectedState"),
            },
            target_kinds=_target_kinds(plan),
        )
        return {
            "stepResults": step_results,
            "verifiedProjectionContext": _canonical(response),
        }

    def verify(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any
    ) -> Mapping[str, Any]:
        plan = prepared["lowering"]["normalizedInput"]
        response = (
            result.get("verifiedProjectionContext")
            if isinstance(result, Mapping)
            else None
        )
        if not isinstance(response, Mapping):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED",
                "Fairlight plan lacks fresh post-mutation projection custody.",
            )
        evidence = list(response.get("evidence") or [])
        if isinstance(response.get("snapshot", {}).get("digest"), str):
            evidence.append(
                {
                    "modality": "structural",
                    "digest": response["snapshot"]["digest"],
                    "summary": "Fresh aggregate Fairlight post-state was read back.",
                }
            )
        if response.get("protectedStatePreserved") is not True or {
            "readback",
            "structural",
        } - {row.get("modality") for row in evidence if isinstance(row, Mapping)}:
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fairlight plan proof is incomplete."
            )
        locators = _locator_by_key(plan, response["targets"])
        current_loudness_bindings = _track_loudness_bindings(
            context, plan, response, locators
        )
        prepared_loudness_bindings = prepared["lowering"].get("trackLoudness", {})
        if {
            key: _loudness_structural_binding(value)
            for key, value in current_loudness_bindings.items()
        } != {
            key: _loudness_structural_binding(value)
            for key, value in prepared_loudness_bindings.items()
        }:
            raise FairlightEvaluationError(
                "STALE_REVISION", "Track loudness target closure changed."
            )
        before_readback = (
            prepared.get("preState", {}).get("snapshot", {}).get("actionReadback")
        )
        current_readback = response.get("snapshot", {}).get("actionReadback")
        step_results = (
            result.get("stepResults") if isinstance(result, Mapping) else None
        )
        if not isinstance(step_results, list) or len(step_results) != len(
            plan["changes"]
        ):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fairlight plan result custody is incomplete."
            )
        for index, (change, results) in enumerate(
            zip(plan["changes"], step_results, strict=True)
        ):
            target = change["target"]
            key = (
                ("clip", target["clipId"])
                if target["kind"] == "clip"
                else (
                    ("track", target["trackIndex"])
                    if target["kind"] == "track"
                    else ("timeline", plan["timelineId"])
                )
            )
            if change.get("kind") == "loudness":
                receipt = (
                    results[0]
                    if isinstance(results, list) and len(results) == 1
                    else None
                )
                prepared_binding = prepared_loudness_bindings.get(str(index))
                current_binding = current_loudness_bindings.get(str(index))
                source_proof = (
                    receipt.get("sourceProof")
                    if isinstance(receipt, Mapping)
                    else None
                )
                if (
                    not isinstance(receipt, Mapping)
                    or not isinstance(prepared_binding, Mapping)
                    or not isinstance(current_binding, Mapping)
                    or receipt.get("rangeDigest")
                    != prepared_binding.get("rangeDigest")
                    or receipt.get("appliedFaderDb")
                    != current_binding.get("originalFaderDb")
                    or not isinstance(source_proof, Mapping)
                    or source_proof.get("status") != "verified"
                ):
                    raise FairlightEvaluationError(
                        "VERIFICATION_FAILED",
                        "Track loudness receipt lacks exact final fader custody.",
                    )
            semantic = _semantic_change(
                change,
                results,
                locators[key],
                before_readback=before_readback,
                current_readback=current_readback,
            )
            expected = change.get(
                "gainDb", change.get("pan", change.get("durationFrames"))
            )
            observed = semantic.get(
                "afterDb",
                semantic.get(
                    "after", semantic.get("afterFrames", semantic.get("afterPresent"))
                ),
            )
            if change.get("kind") == "track_mix":
                expected = {"levelDb": change["levelDb"], "pan": change["pan"]}
            elif change.get("kind") == "clip_fade_curve":
                expected = change["curve"]
            elif change.get("kind") == "effect":
                expected = True
            elif change.get("kind") == "loudness":
                expected = observed
            if observed != expected:
                raise FairlightEvaluationError(
                    "VERIFICATION_FAILED",
                    "Fresh Fairlight plan readback did not match the requested state.",
                )
        verification = {
            "outcome": "passed",
            "evidence": _canonical(evidence),
            "protectedStatePreserved": True,
        }
        result["projectionContext"] = _canonical(response)
        result["carrierVerification"] = verification
        return verification

    def recover(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        _failure: BaseException,
    ) -> Mapping[str, Any]:
        plan = prepared["lowering"]["normalizedInput"]
        try:
            response = _callback(
                self.authority,
                context,
                ACTION_ID,
                "recover",
                {"prepared": prepared},
                target_kinds=_target_kinds(plan),
            )
            recovery = response.get("recovery")
            if (
                isinstance(recovery, Mapping)
                and recovery.get("manualActionRequired") is True
            ):
                return _canonical(recovery)
        except Exception:
            pass
        return {
            "outcome": "manual_required",
            "attempted": True,
            "manualActionRequired": True,
        }

    def project_result(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any
    ) -> Any:
        plan = prepared["lowering"]["normalizedInput"]
        response = (
            result.get("projectionContext") if isinstance(result, Mapping) else None
        )
        step_results = (
            result.get("stepResults") if isinstance(result, Mapping) else None
        )
        if (
            not isinstance(response, Mapping)
            or not isinstance(step_results, list)
            or len(step_results) != len(plan["changes"])
        ):
            raise FairlightEvaluationError(
                "VERIFICATION_FAILED", "Fairlight plan result custody is incomplete."
            )
        locators = _locator_by_key(plan, response["targets"])
        before_readback = (
            prepared.get("preState", {}).get("snapshot", {}).get("actionReadback")
        )
        current_readback = response.get("snapshot", {}).get("actionReadback")
        checks = []
        steps = []
        affected_clips: list[str] = []
        affected_tracks: list[int] = []
        affected_buses: list[dict[str, str]] = []
        for index, (change, results) in enumerate(
            zip(plan["changes"], step_results, strict=True)
        ):
            target = change["target"]
            key = (
                ("clip", target["clipId"])
                if target["kind"] == "clip"
                else (
                    ("track", target["trackIndex"])
                    if target["kind"] == "track"
                    else ("timeline", plan["timelineId"])
                )
            )
            semantic = _semantic_change(
                change,
                results,
                locators[key],
                before_readback=before_readback,
                current_readback=current_readback,
            )
            changed = semantic.get(
                "beforeDb",
                semantic.get(
                    "before",
                    semantic.get("beforeFrames", semantic.get("beforePresent")),
                ),
            ) != semantic.get(
                "afterDb",
                semantic.get(
                    "after", semantic.get("afterFrames", semantic.get("afterPresent"))
                ),
            )
            structural_id = f"evidence_plan_{index:03d}_structural"
            checks.append(
                {
                    "evidenceId": structural_id,
                    "stepIndex": index,
                    "kind": "structural_readback",
                    "status": "passed",
                    "target": target,
                    "summary": "Action-specific Fairlight state matched the requested step.",
                    "stateDigest": _sha({"target": target, "change": semantic}),
                    "artifact": None,
                }
            )
            steps.append(
                {
                    "stepIndex": index,
                    "outcome": "succeeded" if changed else "no_change",
                    "target": target,
                    "change": semantic,
                    "structuralEvidenceId": structural_id,
                    "auditionEvidenceId": None,
                }
            )
            if changed and target["kind"] == "clip":
                affected_clips.append(target["clipId"])
                affected_tracks.append(target["trackIndex"])
            elif changed and target["kind"] == "track":
                affected_tracks.append(target["trackIndex"])
            elif changed and target["kind"] == "bus":
                affected_buses.append(
                    {"busName": target["busName"], "busKind": target["busKind"]}
                )
        any_changed = any(step["outcome"] == "succeeded" for step in steps)
        protected_digest = response["snapshot"]["digest"]
        projected = {
            "actionId": ACTION_ID,
            "projectId": plan["projectId"],
            "timelineId": plan["timelineId"],
            "outcome": "succeeded" if any_changed else "no_change",
            "timelineRevision": response["snapshot"]["revision"],
            "affectedClipIds": list(dict.fromkeys(affected_clips)),
            "affectedTrackIndexes": list(dict.fromkeys(affected_tracks)),
            "affectedBuses": list(
                {
                    f"{row['busKind']}:{row['busName']}": row for row in affected_buses
                }.values()
            ),
            "steps": steps,
            "evidence": {
                "outcome": "passed",
                "structuralReadback": "passed",
                "audition": {
                    "required": False,
                    "status": "not_run",
                },
                "checks": checks,
                "protectedState": {
                    "evidenceId": "evidence_plan_protected_state",
                    "status": "passed",
                    "linkedMedia": "preserved",
                    "unexpectedChanges": False,
                    "stateDigest": protected_digest,
                    "summary": "Linked topology and unrelated tracks were preserved.",
                },
            },
            "recovery": {
                "state": "none",
                "manualRecoveryRequired": False,
                "guidance": None,
            },
        }
        return _canonical(projected)

    def validate_public_result(self, value: Any) -> bool:
        return (
            isinstance(value, Mapping)
            and value.get("actionId") == ACTION_ID
            and isinstance(value.get("steps"), list)
            and bool(value["steps"])
        )


def build_fairlight_plan_prepared_action():
    authority = FairlightEvaluationExecutionAuthority(ACTION_ID)
    return FairlightPlanPreparedActionDescriptor(authority), authority
