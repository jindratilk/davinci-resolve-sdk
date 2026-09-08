"""Truthful result and evidence adapters for the assigned Fairlight routes.

Only authoritative handler readbacks, carrier verification, and fresh
filesystem observations are used. Handler prose is never treated as proof.
"""

from __future__ import annotations

import hashlib
import json
import wave
from typing import Any, Mapping

from .fairlight_runtime_artifacts import artifact_evidence_digest
from .fairlight_runtime_projection_support import FairlightDescriptorError


ASSIGNED_FAIRLIGHT_COMMAND_IDS = frozenset(
    {
        "fairlight.export.audio",
        "fairlight.bounce.mix_to_track",
        "fairlight.bounce.track",
        "fairlight.insert",
        "fairlight.sound_library.delete",
        "fairlight.sound_library.index_file",
        "fairlight.sound_library.index_folder",
        "fairlight.sound_library.insert",
        "fairlight.sound_library.source_rebuild",
        "fairlight.sound_library.source_remove",
    }
)


def handles_fairlight_library_result(command_id: str) -> bool:
    return command_id in ASSIGNED_FAIRLIGHT_COMMAND_IDS


def _candidate(result: Any) -> Mapping[str, Any]:
    candidate = (
        result.get("handlerResult", result) if isinstance(result, Mapping) else None
    )
    if not isinstance(candidate, Mapping):
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Fairlight handler result is not a structured object"
        )
    if candidate.get("dry_run") is True:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "A Fairlight dry-run cannot become a mutation result"
        )
    return candidate


def _scope(value: Mapping[str, Any]) -> str:
    scope = value.get("database")
    if scope not in {"project", "user"}:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Sound Library result lacks an exact database scope"
        )
    return str(scope)


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        value = None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", f"Fairlight result lacks {label}"
        ) from exc
    if number <= 0:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", f"Fairlight result has invalid {label}"
        )
    return number


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        value = None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", f"Fairlight result lacks {label}"
        ) from exc
    if number < 0:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", f"Fairlight result has invalid {label}"
        )
    return number


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", f"Fairlight result lacks {label}"
        )
    return value.strip()


def _library_item(row: Any) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Sound Library readback item is malformed"
        )
    file_info = row.get("file") if isinstance(row.get("file"), Mapping) else {}
    raw_id = _text(row.get("clip_id"), "Sound Library clip id")
    name = _text(row.get("name") or row.get("filename"), "Sound Library item name")
    path = _text(file_info.get("path") or row.get("path"), "Sound Library item path")
    sample_rate = _positive_int(file_info.get("sample_rate"), "sample rate")
    channel_count = _positive_int(file_info.get("channel_count"), "channel count")
    duration_samples = _nonnegative_int(
        file_info.get("duration")
        if file_info.get("duration") is not None
        else row.get("duration"),
        "duration samples",
    )
    frame_rate = file_info.get("frame_rate")
    try:
        frame_rate_number = float(frame_rate)
    except (TypeError, ValueError) as exc:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Sound Library readback lacks timeline frame rate"
        ) from exc
    if frame_rate_number <= 0:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Sound Library readback has invalid timeline frame rate"
        )
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    tags = [
        item.strip()
        for item in metadata.values()
        if isinstance(item, str) and item.strip()
    ]
    public_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:40]
    return {
        "libraryItemId": f"library_item_{public_id}",
        "name": name,
        "path": path,
        "durationFrames": int(
            round(duration_samples / sample_rate * frame_rate_number)
        ),
        "sampleRate": sample_rate,
        "channelCount": channel_count,
        "tags": tags,
    }


def _clip_from_insert(row: Any, context: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Fairlight insert readback lacks an inserted item"
        )
    timeline_id = context.get("timeline", {}).get("timelineId")
    item_id = row.get("timeline_item_id") or row.get("timelineItemId")
    if not isinstance(timeline_id, str) or not timeline_id.startswith("timeline_"):
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Fairlight insert lacks a stable timeline identity"
        )
    if not isinstance(item_id, str) or not item_id.startswith("timeline_item_"):
        raise FairlightDescriptorError(
            "VALIDATION_ERROR",
            "Fairlight insert readback lacks a stable timeline item identity",
        )
    start = _nonnegative_int(row.get("start"), "insert record start")
    end = _nonnegative_int(row.get("end"), "insert record end")
    source_start = _nonnegative_int(row.get("source_start"), "insert source start")
    source_end = _nonnegative_int(row.get("source_end"), "insert source end")
    if (
        end < start
        or source_end < source_start
        or end - start != source_end - source_start
    ):
        raise FairlightDescriptorError(
            "VALIDATION_ERROR",
            "Fairlight insert readback frame ranges are inconsistent",
        )
    return {
        "timelineId": timeline_id,
        "timelineItemId": item_id,
        "clipName": _text(row.get("name"), "inserted clip name"),
        "trackIndex": _positive_int(row.get("track_index"), "insert track index"),
        "range": {
            "recordStartFrame": start,
            "recordEndFrame": end,
            "durationFrames": end - start,
            "sourceStartFrame": source_start,
            "sourceEndFrame": source_end,
        },
    }


def _verified_readback(value: Mapping[str, Any]) -> Mapping[str, Any]:
    verification = value.get("verification")
    if (
        not isinstance(verification, Mapping)
        or verification.get("status") != "verified"
    ):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Fairlight handler lacks a verified structured readback",
        )
    checks = verification.get("checks")
    if (
        not isinstance(checks, list)
        or not checks
        or not all(
            isinstance(check, Mapping) and check.get("ok") is True for check in checks
        )
    ):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight handler readback checks did not all pass"
        )
    return verification


def _protected_proof(value: Mapping[str, Any]) -> Mapping[str, Any]:
    protected = value.get("protected_state")
    if (
        not isinstance(protected, Mapping)
        or not isinstance(protected.get("before"), Mapping)
        or not isinstance(protected.get("after"), Mapping)
        or protected["before"] != protected["after"]
    ):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Fairlight handler lacks protected-state preservation proof",
        )
    return protected


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _public_evidence(
    value: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    file_digest: str | None,
    carrier_verification: Any,
    required_modalities: set[str],
) -> dict[str, Any]:
    _verified_readback(value)
    if carrier_verification is None:
        _protected_proof(value)
        carrier_verification = {
            "outcome": "passed",
            "protectedStatePreserved": True,
            "evidence": [
                {"modality": "readback"},
                {"modality": "structural"},
            ],
        }
    if (
        not isinstance(carrier_verification, Mapping)
        or carrier_verification.get("outcome") != "passed"
        or carrier_verification.get("protectedStatePreserved") is not True
    ):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight carrier verification did not pass"
        )
    evidence = carrier_verification.get("evidence")
    if not isinstance(evidence, list):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight carrier evidence is unavailable"
        )
    modalities = {row.get("modality") for row in evidence if isinstance(row, Mapping)}
    if not required_modalities <= modalities:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight carrier omitted required evidence"
        )
    used_embedded_proof = carrier_verification.get("evidence") == [
        {"modality": "readback"},
        {"modality": "structural"},
        {"modality": "auditioned"},
    ]
    checks = [
        {
            "kind": "structural_readback",
            "status": "passed",
            "summary": "Authoritative structured state readback matched the changed target.",
        }
    ]
    audition_required = "auditioned" in required_modalities
    if audition_required:
        checks.append(
            {
                "kind": "audio_audition",
                "status": "passed",
                "summary": (
                    "Audio audition was bound to the confirmed changed state."
                    if used_embedded_proof
                    else "Fresh target-range audio was rendered after the confirmed change."
                ),
            }
        )
    if file_digest is not None:
        checks.append(
            {
                "kind": "file_probe",
                "status": "passed",
                "summary": "Fresh filesystem content identity was validated.",
            }
        )
    return {
        "checks": checks,
        "audition": {
            "required": audition_required,
            "status": "passed" if audition_required else "not_run",
        },
    }


def _file_state(identity: Mapping[str, Any]) -> dict[str, Any]:
    path = _text(identity.get("path"), "export path")
    if identity.get("kind") != "file" or identity.get("exists") is not True:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight export is not a verified regular file"
        )
    try:
        with wave.open(path, "rb") as stream:
            frames = stream.getnframes()
            sample_rate = stream.getframerate()
            channels = stream.getnchannels()
    except (OSError, EOFError, wave.Error) as exc:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight export audio metadata could not be probed"
        ) from exc
    return {
        "path": path,
        "exists": True,
        "sizeBytes": _nonnegative_int(identity.get("sizeBytes"), "export byte size"),
        "durationFrames": frames,
        "sampleRate": sample_rate,
        "channelCount": channels,
    }


def _after_state(
    command_id: str,
    value: Mapping[str, Any],
    context: Mapping[str, Any],
    fresh_artifacts: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], int, str | None]:
    if command_id in {
        "fairlight.export.audio",
        "fairlight.bounce.mix_to_track",
        "fairlight.bounce.track",
    }:
        identity = fresh_artifacts.get("outputPath")
        if not isinstance(identity, Mapping):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Fairlight export lacks fresh output identity"
            )
        after = _file_state(identity)
        if value.get("output_path") != after["path"]:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED",
                "Fairlight export path disagrees with filesystem proof",
            )
        return (
            {"kind": "output", "path": after["path"]},
            after,
            1,
            artifact_evidence_digest(dict(identity)),
        )

    if command_id in {"fairlight.insert", "fairlight.sound_library.insert"}:
        insert = (
            value.get("insert")
            if command_id.endswith("sound_library.insert")
            else value
        )
        verification = (
            insert.get("verification") if isinstance(insert, Mapping) else None
        )
        rows = (
            verification.get("inserted_items")
            if isinstance(verification, Mapping)
            else None
        )
        if not isinstance(rows, list) or len(rows) != 1:
            raise FairlightDescriptorError(
                "VALIDATION_ERROR",
                "Fairlight insert requires one exact inserted-item readback",
            )
        clip = _clip_from_insert(rows[0], context)
        if command_id == "fairlight.insert":
            after = {"clip": clip, "range": clip["range"]}
        else:
            after = {"item": _library_item(value.get("selected_result")), "clip": clip}
        return {"kind": "timeline", "timelineId": clip["timelineId"]}, after, 1, None

    scope = _scope(value)
    verification = _verified_readback(value)
    target = {"kind": "library", "scope": scope}
    if command_id == "fairlight.sound_library.index_file":
        after = {
            "scope": scope,
            "item": _library_item(verification.get("registered_item")),
        }
        return target, after, 1, None
    if command_id in {
        "fairlight.sound_library.index_folder",
        "fairlight.sound_library.source_rebuild",
    }:
        rows = verification.get("registered_items")
        if not isinstance(rows, list) or not rows:
            raise FairlightDescriptorError(
                "VALIDATION_ERROR",
                "Sound Library folder readback lacks registered items",
            )
        items = [_library_item(row) for row in rows]
        discovery = (
            value.get("discovery")
            if isinstance(value.get("discovery"), Mapping)
            else {}
        )
        source = {
            "path": _text(
                value.get("target", {}).get("path"), "Sound Library source path"
            ),
            "recursive": bool(value.get("recursive", discovery.get("recursive"))),
            "indexedFileCount": len(items),
        }
        return (
            target,
            {"scope": scope, "source": source, "items": items},
            len(items),
            None,
        )
    if command_id == "fairlight.sound_library.source_remove":
        remaining = verification.get("remaining_sources")
        if remaining != []:
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED", "Sound Library source removal is not complete"
            )
        source = {
            "path": _text(
                value.get("target", {}).get("path"), "Sound Library source path"
            ),
            "recursive": bool(value.get("recursive")),
            "indexedFileCount": 0,
        }
        return target, {"scope": scope, "source": source}, 1, None
    if command_id == "fairlight.sound_library.delete":
        rows = verification.get("remaining_items")
        if not isinstance(rows, list):
            raise FairlightDescriptorError(
                "VALIDATION_ERROR",
                "Sound Library delete readback lacks the remaining library state",
            )
        return (
            target,
            {"scope": scope, "items": [_library_item(row) for row in rows]},
            _positive_int(value.get("deleted_count"), "deleted item count"),
            None,
        )
    raise FairlightDescriptorError(
        "VALIDATION_ERROR", "Fairlight result adapter does not own this command"
    )


def project_fairlight_library_result(
    context: Mapping[str, Any],
    descriptor: Any,
    _prepared: Mapping[str, Any],
    result: Any,
    *,
    fresh_artifacts: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project one assigned handler result, failing before any invented success."""

    command_id = descriptor.command_id
    if command_id not in ASSIGNED_FAIRLIGHT_COMMAND_IDS:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Fairlight result adapter does not own this command"
        )
    value = _candidate(result)
    if value.get("action") != command_id or value.get("changed") is not True:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR",
            "Fairlight handler did not report an exact changed action",
        )
    target, after, affected_count, file_digest = _after_state(
        command_id, value, context, fresh_artifacts or {}
    )
    evidence = _public_evidence(
        value,
        after,
        file_digest=file_digest,
        carrier_verification=(
            result.get("carrierVerification") if isinstance(result, Mapping) else None
        ),
        required_modalities=set(
            _prepared.get("verification", {}).get(
                "minimumEvidence", ("readback", "structural")
            )
        ),
    )
    return {
        "actionId": descriptor.action_id,
        "outcome": "succeeded",
        "target": target,
        "before": None,
        "after": after,
        "affectedCount": affected_count,
        "evidence": evidence,
        "recovery": {
            "required": False,
            "manualRecoveryRequired": False,
            "state": "none",
            "guidance": None,
        },
    }


def read_fairlight_library_evidence(
    _context: Mapping[str, Any],
    descriptor: Any,
    prepared: Mapping[str, Any],
    result: Any,
    *,
    fresh_artifacts: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return carrier evidence only after structured proof passes."""

    value = _candidate(result)
    _target, after, _count, file_digest = _after_state(
        descriptor.command_id, value, _context, fresh_artifacts or {}
    )
    protected = _protected_proof(value)
    verification = _verified_readback(value)
    digests = {
        "readback": _digest(verification),
        "structural": _digest(after),
    }
    if file_digest is not None:
        digests["file"] = file_digest
    targets = prepared.get("targets")
    if not isinstance(targets, list) or not targets:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight prepared targets are unavailable"
        )
    return {
        "outcome": "passed",
        "targetEvidence": [
            {
                "targetId": target["stableId"],
                "targetRevision": target["revision"],
                "modality": modality,
                "digest": digest,
                "summary": f"Fresh Fairlight {modality} proof passed.",
            }
            for target in targets
            for modality, digest in sorted(digests.items())
        ],
        "protectedStatePreserved": protected["before"] == protected["after"],
    }


def current_fairlight_library_truth_gaps(command_id: str) -> tuple[str, ...]:
    """Enumerate known current handler gaps without claiming route success."""

    if command_id not in ASSIGNED_FAIRLIGHT_COMMAND_IDS:
        return ()
    gaps = ["protected_state_readback"]
    if command_id in {"fairlight.insert", "fairlight.sound_library.insert"}:
        gaps.extend(("stable_timeline_item_id", "source_frame_range"))
    if command_id == "fairlight.sound_library.delete":
        gaps.append("remaining_library_state")
    return tuple(gaps)
