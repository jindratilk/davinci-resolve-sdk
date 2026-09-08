"""Truthful result projection for the Fairlight clip-mutation slice.

The legacy handlers represented here return useful command diagnostics, but do
not currently return the complete SDK semantic state, a real-audio audition,
or an independent protected-state attestation.  This adapter consequently
accepts only an explicit strict semantic result accompanied by structured
fresh proof.  It never infers truth from messages, field-name substrings, or
the presence of generic ``verified`` values.
"""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import Any, Mapping

from .fairlight_runtime_contract_validator import (
    fairlight_contract_schema,
    validate_fairlight_contract,
)
from .fairlight_runtime_projection_support import FairlightDescriptorError
from .fairlight_runtime_validation import canonical_fairlight_value


FAIRLIGHT_CLIP_MUTATION_COMMAND_IDS = frozenset(
    {
        "fairlight.ai.dialogue_leveler",
        "fairlight.ai.music_remixer",
        "fairlight.ai.voice_isolation",
        "fairlight.channel_map.set",
        "fairlight.clip.delete",
        "fairlight.clip.link",
        "fairlight.clip.move",
        "fairlight.clip.nudge",
        "fairlight.clip.slip",
        "fairlight.clip.split",
        "fairlight.clip.trim",
        "fairlight.clip.unlink",
        "fairlight.effect.add",
        "fairlight.effect.remove",
        "fairlight.effect.set_param",
        "fairlight.elastic.enable",
        "fairlight.elastic.keyframe",
        "fairlight.eq.set",
        "fairlight.item_source.patch",
        "fairlight.transition.add",
    }
)
FAIRLIGHT_CLIP_MUTATION_ACTION_IDS = frozenset(
    f"cutagent.action.{command_id}"
    for command_id in FAIRLIGHT_CLIP_MUTATION_COMMAND_IDS
)

# Every current legacy payload in this slice lacks these success prerequisites.
# Keeping the report explicit lets composition advertise the real integration
# boundary without treating a failed projection as an implementation mystery.
LEGACY_UNPROVEN_REQUIREMENTS = MappingProxyType(
    {
        action_id: tuple(
            requirement
            for requirement in (
                "strict_semantic_result",
                "target_specific_fresh_readback",
                "protected_state_attestation",
            )

        )
        for action_id in sorted(FAIRLIGHT_CLIP_MUTATION_ACTION_IDS)
    }
)

_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_SEMANTIC_KEYS = frozenset(
    {
        "actionId",
        "outcome",
        "target",
        "before",
        "after",
        "affectedCount",
        "evidence",
        "recovery",
    }
)
_PROOF_KEYS = frozenset({"targetEvidence", "protectedState"})
_TARGET_PROOF_KEYS = frozenset(
    {"targetId", "targetRevision", "modality", "digest", "summary", "source"}
)
_PROTECTED_KEYS = frozenset(
    {"status", "beforeDigest", "afterDigest", "source", "targetIds"}
)
_SOURCE_BY_MODALITY = {
    "readback": "fresh_readback",
    "structural": "fresh_readback",
}


def fairlight_clip_legacy_projection_gaps(action_id: str) -> tuple[str, ...] | None:
    """Return the exact missing proof classes for a current legacy payload."""

    return LEGACY_UNPROVEN_REQUIREMENTS.get(action_id)


def _candidate(result: Any) -> Mapping[str, Any]:
    if not isinstance(result, Mapping):
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Fairlight handler result is not a structured object"
        )
    candidate = result.get("handlerResult", result)
    if not isinstance(candidate, Mapping):
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Fairlight handler result is not a structured object"
        )
    return candidate


def _semantic_result(
    descriptor: Any, candidate: Mapping[str, Any]
) -> Mapping[str, Any]:
    explicit = candidate.get("semanticResult", candidate.get("semantic_result"))
    if explicit is None and _SEMANTIC_KEYS <= set(candidate):
        explicit = {key: candidate[key] for key in _SEMANTIC_KEYS}
    if not isinstance(explicit, Mapping):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Fairlight handler omitted its strict action-specific semantic result",
        )
    action = candidate.get("action")
    if action is not None and action != descriptor.command_id:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight handler result belongs to another action"
        )
    projected = canonical_fairlight_value(explicit)
    if projected.get("actionId") != descriptor.action_id:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight semantic result is not action-bound"
        )
    validate_fairlight_contract(
        projected,
        fairlight_contract_schema(descriptor.action_id, "result"),
        "result",
    )
    if projected.get("outcome") != "succeeded":
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Fairlight mutation success projection requires a succeeded semantic result",
        )
    audition = projected.get("evidence", {}).get("audition", {})
    checks = projected.get("evidence", {}).get("checks", [])
    passed_kinds = {
        item.get("kind")
        for item in checks
        if isinstance(item, Mapping) and item.get("status") == "passed"
    }
    required_kinds = {"structural_readback"}
    expected_audition = {"required": False, "status": "not_run"}
    if audition != expected_audition or not required_kinds <= passed_kinds:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Fairlight semantic result lacks required readback or audition truth",
        )
    return projected


def _prepared_targets(prepared: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw_targets = prepared.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Prepared Fairlight targets are unavailable"
        )
    targets: dict[str, Mapping[str, Any]] = {}
    for target in raw_targets:
        stable_id = target.get("stableId") if isinstance(target, Mapping) else None
        revision = target.get("revision") if isinstance(target, Mapping) else None
        if (
            not isinstance(stable_id, str)
            or not stable_id
            or stable_id in targets
            or not isinstance(revision, str)
            or not revision
        ):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Prepared Fairlight target binding is invalid"
            )
        targets[stable_id] = target
    return targets


def _require_semantic_target_binding(
    semantic: Mapping[str, Any], targets: Mapping[str, Mapping[str, Any]]
) -> None:
    target = semantic.get("target")
    clip = target.get("clip") if isinstance(target, Mapping) else None
    item_id = clip.get("timelineItemId") if isinstance(clip, Mapping) else None
    if not isinstance(item_id, str) or item_id not in targets:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Fairlight semantic result does not identify an exact prepared target",
        )


def _verification_evidence(value: Any) -> Mapping[str, Any]:
    proof = value
    if not isinstance(proof, Mapping) or set(proof) != _PROOF_KEYS:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Independent Fairlight verifier omitted structured verification evidence",
        )
    return proof


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _validate_protected_state(proof: Mapping[str, Any], target_ids: set[str]) -> None:
    protected = proof.get("protectedState")
    if not isinstance(protected, Mapping) or set(protected) != _PROTECTED_KEYS:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight protected-state proof is incomplete"
        )
    before = protected.get("beforeDigest")
    after = protected.get("afterDigest")
    if (
        protected.get("status") != "passed"
        or protected.get("source") != "fresh_readback"
        or not _valid_digest(before)
        or after != before
        or protected.get("targetIds") != sorted(target_ids)
    ):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight protected state was not proven preserved"
        )


def _project_target_evidence(
    proof: Mapping[str, Any],
    targets: Mapping[str, Mapping[str, Any]],
    required: set[str],
) -> list[dict[str, str]]:
    raw = proof.get("targetEvidence")
    if not isinstance(raw, list) or not raw:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight target-specific evidence is unavailable"
        )
    output: list[dict[str, str]] = []
    covered: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != _TARGET_PROOF_KEYS:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight target evidence is malformed"
            )
        target_id = item.get("targetId")
        modality = item.get("modality")
        expected_source = _SOURCE_BY_MODALITY.get(modality)
        target = targets.get(target_id) if isinstance(target_id, str) else None
        summary = item.get("summary")
        if (
            target is None
            or item.get("targetRevision") != target.get("revision")
            or modality not in required
            or item.get("source") != expected_source
            or not _valid_digest(item.get("digest"))
            or not isinstance(summary, str)
            or not 1 <= len(summary) <= 500
        ):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight target evidence is not authoritative"
            )
        pair = (target_id, modality)
        if pair in covered:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight target evidence is inconsistent"
            )
        covered.add(pair)
        output.append({key: item[key] for key in _TARGET_PROOF_KEYS - {"source"}})
    expected = {(target_id, modality) for target_id in targets for modality in required}
    if covered != expected:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Fairlight evidence does not cover every exact target and modality",
        )
    return output


def _runtime_clip(locator: Any, timeline_id: Any) -> dict[str, Any]:
    if not isinstance(locator, Mapping) or locator.get("kind") != "clip":
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight runtime omitted its exact clip locator"
        )
    values = {
        "timelineId": timeline_id,
        "timelineItemId": locator.get("stableId"),
        "clipName": locator.get("clipName"),
        "trackIndex": locator.get("trackIndex"),
    }
    start = locator.get("recordStartFrame")
    end = locator.get("recordEndFrameExclusive")
    source_start = locator.get("sourceStartFrame")
    source_end = locator.get("sourceEndFrameExclusive")
    if (
        not isinstance(timeline_id, str)
        or not all(
            isinstance(values[key], str) and values[key]
            for key in ("timelineItemId", "clipName")
        )
        or not isinstance(values["trackIndex"], int)
        or isinstance(values["trackIndex"], bool)
        or values["trackIndex"] < 1
        or any(
            not isinstance(item, int) or isinstance(item, bool)
            for item in (start, end, source_start, source_end)
        )
        or end < start
        or source_end < source_start
    ):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight runtime clip locator is incomplete"
        )
    values["range"] = {
        "recordStartFrame": start,
        "recordEndFrame": end,
        "durationFrames": end - start,
        "sourceStartFrame": source_start,
        "sourceEndFrame": source_end,
    }
    return values


def _runtime_carrier_evidence(
    verification: Any, *, changed: bool, audition_required: bool = False
) -> dict[str, Any]:
    if (
        not isinstance(verification, Mapping)
        or verification.get("outcome") != "passed"
        or verification.get("protectedStatePreserved") is not True
    ):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight carrier verification did not pass"
        )
    rows = verification.get("evidence")
    if not isinstance(rows, list):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight carrier evidence is unavailable"
        )
    modalities = {row.get("modality") for row in rows if isinstance(row, Mapping)}
    required = {"readback", "structural"}
    if audition_required:
        required.add("auditioned")
    if not required <= modalities:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Fairlight carrier evidence lacks required modalities",
        )
    structural = next(
        row
        for row in rows
        if isinstance(row, Mapping) and row.get("modality") == "structural"
    )
    auditioned = next(
        (
            row
            for row in rows
            if isinstance(row, Mapping) and row.get("modality") == "auditioned"
        ),
        None,
    )
    checks = [
        {
            "kind": "structural_readback",
            "status": "passed",
            "summary": str(
                structural.get("summary") or "Fresh Fairlight state read back."
            ),
        }
    ]
    if changed and audition_required:
        checks.append(
            {
                "kind": "audio_audition",
                "status": "passed",
                "summary": str(
                    auditioned.get("summary") or "Fresh affected audio rendered."
                ),
            }
        )
    return {
        "checks": checks,
        "audition": {
            "required": changed and audition_required,
            "status": "passed" if changed and audition_required else "not_run",
        },
    }


def _runtime_handler(result: Any, command_id: str) -> Mapping[str, Any]:
    candidate = _candidate(result)
    if candidate.get("dry_run") is True:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Dry-run output is not mutation evidence"
        )
    action = candidate.get("action")
    if action not in {None, command_id, "edit.blade"}:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight handler result belongs to another action"
        )
    verification = candidate.get("verification")
    if isinstance(verification, Mapping):
        status = verification.get("status")
        if status not in {None, "verified"}:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight handler verification did not pass"
            )
        checks = verification.get("checks")
        if checks is not None and (
            not isinstance(checks, list)
            or any(
                not isinstance(check, Mapping) or check.get("ok") is not True
                for check in checks
            )
        ):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight handler checks did not pass"
            )
    return candidate


def _runtime_plugin(
    readback: Any, requested: Any, *, required: bool, removed: Any = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plugins = readback.get("plugins") if isinstance(readback, Mapping) else None
    summary = readback.get("summary") if isinstance(readback, Mapping) else None
    summary_plugins = summary.get("plugins") if isinstance(summary, Mapping) else None
    # `fairlight effect list` keeps compact slot rows in `plugins` and the
    # authoritative parameter maps in `summary.plugins`. Prefer the latter for
    # semantic mutation projection when present.
    if isinstance(summary_plugins, list):
        plugins = summary_plugins
    normalized_requested = (
        requested.casefold().replace("_", " ").replace("-", " ")
        if isinstance(requested, str)
        else ""
    )
    native_voice = (
        readback.get("native_voice_isolation")
        if isinstance(readback, Mapping) and normalized_requested == "voice isolation"
        else None
    )
    if isinstance(native_voice, Mapping):
        enabled = native_voice.get("isEnabled")
        amount = native_voice.get("amount")
        if not isinstance(enabled, bool) or not isinstance(amount, (int, float)):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Native Voice Isolation readback is incomplete"
            )
        plugins = [
            row
            for row in (plugins if isinstance(plugins, list) else [])
            if not (
                isinstance(row, Mapping)
                and str(row.get("name") or "").casefold() == "voice isolation"
            )
        ]
        if enabled:
            plugins.append(
                {
                    "plugin_id": "bmd:VoiceIsolation:1",
                    "name": "Voice Isolation",
                    "params": {"BMDVoiceIsolationControl::DRY_MIX": amount / 100},
                }
            )
    if not isinstance(plugins, list) or not isinstance(requested, str) or not requested:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight effect readback is incomplete"
        )
    needle = normalized_requested
    matches = [
        row
        for row in plugins
        if isinstance(row, Mapping)
        and needle
        in {
            str(row.get("plugin_id") or "")
            .casefold()
            .replace("_", " ")
            .replace("-", " "),
            str(row.get("name") or "").casefold().replace("_", " ").replace("-", " "),
        }
    ]
    if required and len(matches) != 1:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Fairlight effect readback did not identify one exact effect",
        )
    if not required and matches:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Removed Fairlight effect remains present"
        )
    if matches:
        row = matches[0]
    elif isinstance(removed, Mapping):
        row = {
            "plugin_id": removed.get("plugin_id") or removed.get("key"),
            "name": removed.get("name"),
            "params": {},
        }
    else:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Removed Fairlight effect identity is unavailable"
        )
    params = row.get("params")
    if not isinstance(params, Mapping):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight effect parameters are incomplete"
        )
    return (
        {
            "effectId": str(row.get("plugin_id") or ""),
            "displayName": str(row.get("name") or ""),
            "slotIndex": plugins.index(row) + 1 if matches else 1,
            "enabled": required,
        },
        [
            {"name": str(name), "value": value, "writable": True}
            for name, value in sorted(params.items(), key=lambda item: str(item[0]))
            if isinstance(value, (int, float, bool))
        ],
    )


def _runtime_channel_map(value: Any) -> dict[str, Any]:
    mapping = value.get("mapping") if isinstance(value, Mapping) else None
    if isinstance(mapping, Mapping) and isinstance(mapping.get("channels"), Mapping):
        channels = mapping["channels"]
        rows = channels.get("channels")
        count = channels.get("channelCount")
        if isinstance(rows, list) and count == len(rows):
            return {"channelCount": count, "channels": rows}
    tracks = mapping.get("track_mapping") if isinstance(mapping, Mapping) else None
    if not isinstance(tracks, Mapping):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight channel-map readback is incomplete"
        )
    rows = [
        {
            "sourceChannel": int(source),
            "destinationChannel": int(destination),
            "enabled": not bool(record.get("mute", False)),
        }
        for destination, record in sorted(tracks.items(), key=lambda item: str(item[0]))
        if isinstance(record, Mapping)
        for source in record.get("channel_idx", ())
    ]
    return {"channelCount": len(rows), "channels": rows}


def _effect_param_expectation(
    requested: Mapping[str, Any], handler: Mapping[str, Any]
) -> tuple[Any, Any]:
    expected_name = requested.get("param")
    expected_value = requested.get("value")
    handler_param = handler.get("param")
    value_mapping = handler.get("value_mapping")
    if not isinstance(value_mapping, Mapping) or "native_amount" not in value_mapping:
        resolved_name = handler_param.get("resolved") if isinstance(handler_param, Mapping) else None
        return resolved_name or expected_name, expected_value
    requested_param = "".join(
        character
        for character in str(expected_name or "").casefold()
        if character.isalnum()
    )
    requested_value = requested.get("value")
    native_amount = value_mapping.get("native_amount")
    canonical_name = "BMDVoiceIsolationControl::DRY_MIX"
    resolved_name = handler_param.get("resolved") if isinstance(handler_param, Mapping) else None
    if (
        requested_param not in {"drymix", "bmdvoiceisolationcontroldrymix"}
        or not isinstance(requested_value, (int, float))
        or isinstance(requested_value, bool)
        or not 0 <= requested_value <= 1
        or not isinstance(native_amount, int)
        or isinstance(native_amount, bool)
        or native_amount != int(round(requested_value * 100))
        or resolved_name != canonical_name
    ):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Voice Isolation parameter normalization differs from the signed request",
        )
    return canonical_name, native_amount / 100


def project_fairlight_clip_runtime_result(
    context: Mapping[str, Any],
    descriptor: Any,
    prepared: Mapping[str, Any],
    result: Any,
    response: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Project real carrier-owned clip mutation state without handler-authored semantics."""

    if descriptor.action_id not in FAIRLIGHT_CLIP_MUTATION_ACTION_IDS:
        return None
    handler = _runtime_handler(result, descriptor.command_id)
    private = context.get("privateBindings", {}).get("fairlight", {})
    before_locators = private.get("targets") if isinstance(private, Mapping) else None
    current_locators = response.get("targets")
    if not isinstance(before_locators, (list, tuple)) or not isinstance(
        current_locators, (list, tuple)
    ):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight clip target custody is unavailable"
        )
    before_locator = next(
        (
            row
            for row in before_locators
            if isinstance(row, Mapping) and row.get("kind") == "clip"
        ),
        None,
    )
    current_locator = next(
        (
            row
            for row in current_locators
            if isinstance(row, Mapping) and row.get("kind") == "clip"
        ),
        None,
    )
    timeline_id = (
        context.get("exactRequestBinding", {}).get("identities", {}).get("timelineId")
    )
    before_clip = _runtime_clip(before_locator, timeline_id)
    command_id = descriptor.command_id
    changed = handler.get("changed") is not False
    minimum_evidence = prepared.get("verification", {}).get("minimumEvidence")
    audition_required = (
        "auditioned" in minimum_evidence
        if isinstance(minimum_evidence, (list, tuple, set, frozenset))
        else False
    )
    evidence = _runtime_carrier_evidence(
        verification,
        changed=changed,
        audition_required=audition_required,
    )
    base = {
        "actionId": descriptor.action_id,
        "outcome": "succeeded" if changed else "no_change",
        "target": {"kind": "clip", "clip": before_clip},
        "before": None,
        "after": None,
        "affectedCount": 1 if changed else 0,
        "evidence": evidence,
        "recovery": {
            "required": False,
            "manualRecoveryRequired": False,
            "state": "none",
            "guidance": None,
        },
    }
    if not changed:
        validate_fairlight_contract(
            base, fairlight_contract_schema(descriptor.action_id, "result"), "result"
        )
        return canonical_fairlight_value(base)
    requested = prepared.get("lowering", {}).get("normalizedInput", {})
    readback = response.get("currentReadback")
    current_clip = (
        _runtime_clip(current_locator, timeline_id)
        if current_locator and current_locator.get("exists") is not False
        else None
    )
    if command_id == "fairlight.channel_map.set":
        if current_clip is None:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Mapped Fairlight clip disappeared"
            )
        channels = _runtime_channel_map(readback)
        if channels.get("channels") != requested.get("channels"):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED",
                "Fairlight channel-map readback differs from request",
            )
        after = {"clip": current_clip, "channels": channels}
    elif command_id == "fairlight.clip.delete":
        if current_locator is None or current_locator.get("exists") is not False:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Deleted Fairlight clip still exists"
            )
        after = {"clip": before_clip}
    elif command_id in {"fairlight.clip.link", "fairlight.clip.unlink"}:
        if current_clip is None:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Linked Fairlight clip disappeared"
            )
        linked = current_locator.get("linkedItemIds")
        if not isinstance(linked, list):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight link readback is incomplete"
            )
        expected_ids = {
            row.get("stableId")
            for row in before_locators
            if isinstance(row, Mapping) and row.get("kind") == "clip"
        }
        if command_id.endswith(".link") and not expected_ids.difference(
            {before_clip["timelineItemId"]}
        ) <= set(linked):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED",
                "Fairlight link readback did not contain every signed peer",
            )
        if command_id.endswith(".unlink") and set(linked) & expected_ids.difference(
            {before_clip["timelineItemId"]}
        ):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED",
                "Fairlight unlink readback retained a signed peer",
            )
        after = {"clip": current_clip, "linkedItemIds": linked}
    elif command_id in {
        "fairlight.clip.move",
        "fairlight.clip.nudge",
        "fairlight.clip.trim",
    }:
        if current_clip is None:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight clip range readback is unavailable"
            )
        after = {"clip": current_clip, "range": current_clip["range"]}
    elif command_id in {"fairlight.clip.slip", "fairlight.item_source.patch"}:
        if current_clip is None:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight source-range readback is unavailable"
            )
        after = {"clip": current_clip, "sourceRange": current_clip["range"]}
    elif command_id == "fairlight.clip.split":
        segments = response.get("createdSegments")
        if not isinstance(segments, list) or len(segments) < 2:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight split segment readback is incomplete"
            )
        after = {
            "original": before_clip,
            "segments": [
                _runtime_clip({"kind": "clip", **row}, timeline_id) for row in segments
            ],
        }
        base["affectedCount"] = len(after["segments"])
    elif command_id.startswith("fairlight.ai."):
        key = command_id.removeprefix("fairlight.ai.")
        state_key = {
            "voice_isolation": "voice_isolation",
            "dialogue_leveler": "dialogue_leveler",
            "music_remixer": "music_remixer",
        }[key]
        state = readback.get(state_key) if isinstance(readback, Mapping) else None
        if not isinstance(state, Mapping) or current_clip is None:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight AI readback is incomplete"
            )
        if key == "voice_isolation":
            settings = {"enabled": True, "amount": state.get("amount")}
        elif key == "dialogue_leveler":
            settings = {
                "enabled": True,
                "lifter": state.get("lifter_on"),
                "cleaner": state.get("cleaner_on"),
                "gainDb": state.get("output_gain"),
            }
        else:
            settings = {
                "enabled": True,
                **{
                    name: state.get(name)
                    for name in ("voice", "drums", "bass", "other", "guitar")
                },
            }
        after = {"clip": current_clip, "settings": settings}
    elif command_id.startswith("fairlight.effect."):
        required = command_id != "fairlight.effect.remove"
        effect, parameters = _runtime_plugin(
            readback,
            requested.get("effect"),
            required=required,
            removed=handler.get("effect"),
        )
        if command_id == "fairlight.effect.set_param":
            expected_name, expected_value = _effect_param_expectation(
                requested, handler
            )
            matches = [
                row for row in parameters if row["name"] == expected_name
            ]
            observed_value = matches[0]["value"] if len(matches) == 1 else None
            numeric_match = (
                isinstance(observed_value, (int, float))
                and not isinstance(observed_value, bool)
                and isinstance(expected_value, (int, float))
                and not isinstance(expected_value, bool)
                and abs(float(observed_value) - float(expected_value)) <= 1e-6
            )
            if len(matches) != 1 or not (observed_value == expected_value or numeric_match):
                raise FairlightDescriptorError(
                    "VERIFICATION_FAILED",
                    "Fairlight effect parameter readback differs from request",
                )
        after = {"effect": effect, "parameters": parameters}
    elif command_id.startswith("fairlight.elastic."):
        state = handler.get("state")
        points = []
        if not isinstance(state, Mapping) and command_id.endswith(".enable"):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight Elastic Wave state is incomplete"
            )
        if command_id.endswith(".keyframe"):
            timemap = handler.get("new_timemap")
            raw_points = (
                timemap.get("keyframes") if isinstance(timemap, Mapping) else None
            )
            fps = handler.get("timeline_fps")
            if (
                isinstance(raw_points, list)
                and len(raw_points) >= 2
                and isinstance(fps, (int, float))
                and not isinstance(fps, bool)
                and fps > 0
            ):
                converted = []
                for index, point in enumerate(raw_points):
                    if (
                        not isinstance(point, Mapping)
                        or not isinstance(point.get("x"), (int, float))
                        or not isinstance(point.get("y"), (int, float))
                    ):
                        raise FairlightDescriptorError(
                            "VERIFICATION_FAILED",
                            "Fairlight Elastic Wave point is malformed",
                        )
                    neighbor = (
                        raw_points[index + 1]
                        if index + 1 < len(raw_points)
                        else raw_points[index - 1]
                    )
                    dx = abs(float(neighbor["x"]) - float(point["x"]))
                    dy = abs(float(neighbor["y"]) - float(point["y"]))
                    if dx <= 0 or dy <= 0:
                        raise FairlightDescriptorError(
                            "VERIFICATION_FAILED",
                            "Fairlight Elastic Wave point speed is unproven",
                        )
                    converted.append(
                        {
                            "recordFrame": current_clip["range"]["recordStartFrame"]
                            + round(float(point["x"]) * float(fps)),
                            "sourceFrame": current_clip["range"]["sourceStartFrame"]
                            + round(float(point["y"]) * float(fps)),
                            "speed": dy / dx,
                        }
                    )
                points = converted
            else:
                value = current_clip["range"]
                duration = value["recordEndFrame"] - value["recordStartFrame"]
                source_duration = value["sourceEndFrame"] - value["sourceStartFrame"]
                if duration <= 0 or source_duration <= 0:
                    raise FairlightDescriptorError(
                        "VERIFICATION_FAILED",
                        "Fairlight Elastic Wave linear mapping is unproven",
                    )
                speed = source_duration / duration
                points = [
                    {
                        "recordFrame": value["recordStartFrame"],
                        "sourceFrame": value["sourceStartFrame"],
                        "speed": speed,
                    },
                    {
                        "recordFrame": value["recordEndFrame"],
                        "sourceFrame": value["sourceEndFrame"],
                        "speed": speed,
                    },
                ]
        after = {
            "clip": current_clip,
            "enabled": bool((state or {}).get("enabled", True)),
            "points": points,
        }
    elif command_id == "fairlight.eq.set":
        raw_bands = handler.get("bands") or handler.get("parsed_bands")
        if not isinstance(raw_bands, list):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight EQ handler omitted normalized bands"
            )
        bands = []
        for band in raw_bands:
            if not isinstance(band, Mapping):
                raise FairlightDescriptorError(
                    "VERIFICATION_FAILED", "Fairlight EQ band is malformed"
                )
            bands.append(
                {
                    "band": band.get("band"),
                    "enabled": bool(band.get("enabled", True)),
                    "filterType": band.get("filterType", band.get("shape")),
                    "frequencyHz": band.get("frequencyHz", band.get("freq_hz")),
                    "gainDb": band.get("gainDb", band.get("gain_db")),
                    "q": band.get("q"),
                }
            )
        after = {"clip": current_clip, "enabled": True, "bands": bands}
    elif command_id == "fairlight.transition.add":
        transition_type = handler.get("transition_type") or requested.get(
            "transitionType"
        )
        duration = handler.get("duration_frames")
        if not isinstance(duration, int) or isinstance(duration, bool) or duration < 1:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight transition readback omitted duration"
            )
        after = {
            "clip": current_clip,
            "transitionType": transition_type,
            "durationFrames": duration,
        }
    else:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight clip runtime projection is unavailable"
        )
    if after is None or ("clip" in after and after["clip"] is None):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight action-specific post-state is unavailable"
        )
    base["after"] = after
    validate_fairlight_contract(
        base, fairlight_contract_schema(descriptor.action_id, "result"), "result"
    )
    return canonical_fairlight_value(base)


def project_fairlight_clip_mutation_result(
    _context: Mapping[str, Any],
    descriptor: Any,
    prepared: Mapping[str, Any],
    result: Any,
) -> Mapping[str, Any] | None:
    """Project one in-slice result, or return ``None`` for another action."""

    if descriptor.action_id not in FAIRLIGHT_CLIP_MUTATION_ACTION_IDS:
        return None
    candidate = _candidate(result)
    semantic = _semantic_result(descriptor, candidate)
    targets = _prepared_targets(prepared)
    _require_semantic_target_binding(semantic, targets)
    return semantic


def read_fairlight_clip_mutation_evidence(
    _context: Mapping[str, Any],
    descriptor: Any,
    prepared: Mapping[str, Any],
    result: Any,
    *,
    independent_evidence: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    """Return host verification proof for one in-slice result."""

    if descriptor.action_id not in FAIRLIGHT_CLIP_MUTATION_ACTION_IDS:
        return None
    candidate = _candidate(result)
    semantic = _semantic_result(descriptor, candidate)
    targets = _prepared_targets(prepared)
    _require_semantic_target_binding(semantic, targets)
    proof = _verification_evidence(independent_evidence)
    target_ids = set(targets)
    _validate_protected_state(proof, target_ids)
    required = set(prepared.get("verification", {}).get("minimumEvidence", ()))
    if not required or not required <= set(_SOURCE_BY_MODALITY):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight verification policy is unsupported"
        )
    evidence = _project_target_evidence(proof, targets, required)
    return {
        "outcome": "passed",
        "targetEvidence": evidence,
        "protectedStatePreserved": True,
    }
