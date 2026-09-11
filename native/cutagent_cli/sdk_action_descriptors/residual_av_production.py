"""Production exact-state and managed-artifact authority for residual AV actions."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from ..errors import ValidationError
from .residual_av import RESIDUAL_AV_ACTION_DESCRIPTORS
from .residual_av_handler_runtime import ResidualAvHandlerExecutionAuthority


_DESCRIPTORS = {item.action_id: item for item in RESIDUAL_AV_ACTION_DESCRIPTORS}
_PATH_FIELDS = (
    "inputPath",
    "referencePath",
    "targetPath",
    "templatePath",
    "imagePath",
    "outputPath",
    "path",
)
PRODUCTION_VERIFIED_RESIDUAL_AV_ACTIONS = frozenset(
    {
        "cutagent.action.audio.beat_detect",
        "cutagent.action.audio.waveform_offset",
        "cutagent.action.audio.info",
        "cutagent.action.burnin.load",
        "cutagent.action.burnin.preset.export",
        "cutagent.action.burnin.preset.import",
        "cutagent.action.clip.offset",
        "cutagent.action.clip.marker.add",
        "cutagent.action.clip.marker.custom_data",
        "cutagent.action.clip.marker.delete",
        "cutagent.action.clip.marker.delete_custom",
        *(
            action_id
            for action_id in _DESCRIPTORS
            if action_id.startswith("cutagent.action.edit.")
        ),
    }
)
_SINGLE_RESULT_VALIDATION_ACTIONS = frozenset(
    {
        # These reads are calculations over one exact admitted input. Validate
        # their result structure and input-derived invariants without repeating
        # the potentially expensive underlying calculation.
        "cutagent.action.audio.beat_detect",
        "cutagent.action.audio.waveform_offset",
        "cutagent.action.clip.offset",
    }
)


def _stable_ordinary_timeline_items(snapshot):
    """Compare timeline content while ignoring snapshot-identity churn."""
    items = {}
    for track in snapshot.get("tracks", ()):
        stable_track = {
            key: deepcopy(track.get(key))
            for key in ("type", "index", "name", "enabled", "locked")
            if key in track
        }
        for clip in track.get("clips", ()):
            item_id = clip.get("id")
            if not isinstance(item_id, str):
                continue
            stable_clip = {
                key: deepcopy(value)
                for key, value in clip.items()
                if key not in {"snapshotId", "snapshotRevision", "snapshotTrackId"}
            }
            items[item_id] = (stable_track, stable_clip)
    return items


def _semantic_data_with_artifact_readback(action_id, data, context, value=None):
    semantic = deepcopy(dict(data))
    if action_id == "cutagent.action.audio.waveform_offset":
        normalized = value if isinstance(value, Mapping) else {}
        confidence = semantic.get("confidence")
        try:
            fps = float(normalized.get("fps", 24.0))
            offset_seconds = float(semantic["offset_seconds"])
            offset_frames = float(semantic["offset_frames_float"])
            drift_frames = float(semantic["drift_span_ms"]) * fps / 1000.0
            peak_quality = float(confidence["median_peak_quality"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValidationError("Waveform offset readback is incomplete.") from exc
        if not all(math.isfinite(item) for item in (
            fps, offset_seconds, offset_frames, drift_frames, peak_quality
        )) or fps <= 0 or drift_frames < 0 or peak_quality < 0:
            raise ValidationError("Waveform offset readback is invalid.")
        semantic.update(
            fps=fps,
            offset_frames=offset_frames,
            drift_frames=drift_frames,
            confidence=min(1.0, peak_quality),
        )
        return semantic
    if action_id != "cutagent.action.audio.reverb":
        return semantic
    output = context.get("privateBindings", {}).get("artifacts", {}).get("output")
    if not isinstance(output, Mapping) or not isinstance(output.get("resolvedPath"), str):
        raise ValidationError("Reverb result lacks carrier-owned output custody.")
    from ..core import audio_ops

    stream = audio_ops.info(output["resolvedPath"])
    try:
        duration = float(stream["duration"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValidationError("Reverb output readback omitted a valid duration.") from exc
    if not math.isfinite(duration) or duration < 0:
        raise ValidationError("Reverb output readback omitted a valid duration.")
    semantic["durationSeconds"] = duration
    return semantic


def _mutable_copy(value: Any) -> Any:
    """Thaw carrier-frozen values without asking deepcopy to pickle proxies."""

    if isinstance(value, Mapping):
        return {key: _mutable_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mutable_copy(item) for item in value]
    return deepcopy(value)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest(value: Any) -> str:
    return _digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    )


def _linked_topology(
    snapshot: Mapping[str, Any], excluded_ids: set[str] | None = None
) -> dict[str, Any]:
    excluded_ids = excluded_ids or set()
    edges = set()
    for track in snapshot.get("tracks", ()):
        for clip in track.get("clips", ()):
            clip_id = clip.get("id")
            if not isinstance(clip_id, str):
                continue
            for linked_id in clip.get("linkedItemIds", ()):
                if (
                    not isinstance(linked_id, str)
                    or clip_id in excluded_ids
                    or linked_id in excluded_ids
                ):
                    continue
                edges.add(tuple(sorted((clip_id, linked_id))))
    rows = [list(edge) for edge in sorted(edges)]
    return {"snapshotDigest": _digest(rows), "edges": rows}


def _unrelated_inspector_state(
    snapshot: Mapping[str, Any], target_ids: set[str]
) -> dict[str, Any]:
    rows = []
    for track in snapshot.get("tracks", ()):
        for clip in track.get("clips", ()):
            clip_id = clip.get("id")
            if not isinstance(clip_id, str) or clip_id in target_ids:
                continue
            rows.append(
                {
                    "trackType": track.get("type"),
                    "trackIndex": track.get("index"),
                    "clip": {
                        key: deepcopy(item)
                        for key, item in clip.items()
                        if key
                        not in {
                            "snapshotId",
                            "snapshotRevision",
                            "snapshotTrackId",
                            "revision",
                            "linkedItemIds",
                        }
                    },
                }
            )
    state = {
        "projectId": snapshot.get("project", {}).get("id"),
        "timelineId": snapshot.get("timeline", {}).get(
            "id", snapshot.get("timelineId")
        ),
        "items": sorted(rows, key=lambda item: str(item["clip"].get("id"))),
    }
    return {"digest": _digest(state), "snapshot": state}


class ResidualAvProductionAuthority(ResidualAvHandlerExecutionAuthority):
    """Carrier-bound authority using fresh timeline/artifact readback and real handlers."""

    def __init__(self):
        self._inspector = None
        self._handler_results: dict[str, Any] = {}
        super().__init__(
            resolve_exact=self._resolve,
            resolve_managed_artifact=self._artifact,
            recover=self._recover,
        )

    def bind_private_timeline_inspector(self, inspector):
        if not callable(inspector):
            raise TypeError("Residual private timeline inspector must be callable.")
        self._inspector = inspector

    def _fusion_before_references(
        self, context: Mapping[str, Any], *, operation: str
    ) -> list[dict[str, Any]]:
        private = context.get("privateBindings")
        before = (
            private.get("fusionBeforeReferences")
            if isinstance(private, Mapping)
            else None
        )
        if not isinstance(before, (list, tuple)):
            raise ValidationError(
                f"Residual Fusion {operation} lacks exact pre-{operation} collection custody."
            )
        if any(not isinstance(item, Mapping) for item in before):
            raise ValidationError(
                f"Residual Fusion pre-{operation} collection is malformed."
            )
        return [self._fusion_reference(item) for item in before]

    @staticmethod
    def _roots() -> tuple[Path, ...]:
        roots = []
        for key in (
            "CUTAGENT_USER_UPLOADS_DIR",
            "CUTAGENT_USER_EXPORTS_DIR",
            "CUTAGENT_CHECKPOINT_DIR",
            "CUTAGENT_ARTIFACTS_DIR",
        ):
            value = os.environ.get(key)
            if value:
                roots.append(Path(value).expanduser().resolve(strict=False))
        if not roots:
            raise ValidationError("Residual managed-artifact roots are unavailable.")
        return tuple(dict.fromkeys(roots))

    def _managed_path(self, raw: str) -> tuple[Path, Path]:
        if not isinstance(raw, str) or not raw:
            raise ValidationError("Residual managed-artifact path is invalid.")
        path = Path(raw).expanduser().resolve(strict=False)
        matches = [
            root for root in self._roots() if path == root or root in path.parents
        ]
        if len(matches) != 1:
            raise ValidationError("Residual artifact escaped one exact managed root.")
        current = path
        while current != matches[0]:
            if current.exists() and current.is_symlink():
                raise ValidationError(
                    "Residual managed artifact cannot traverse a symlink."
                )
            current = current.parent
        return path, matches[0]

    def _artifact(self, raw: str) -> Mapping[str, Any]:
        path, root = self._managed_path(raw)
        if not path.is_file() or path.is_symlink():
            raise ValidationError(
                "Managed input artifact is unavailable or not a regular file."
            )
        data = path.read_bytes()
        digest = _digest_bytes(data)
        return {
            "stableId": f"artifact_{hashlib.sha256(str(path).encode()).hexdigest()[:32]}",
            "revision": f"revision_{hashlib.sha256((str(path) + digest).encode()).hexdigest()[:32]}",
            "digest": digest,
            "allowedRootId": f"managed_root_{hashlib.sha256(str(root).encode()).hexdigest()[:24]}",
            "resolvedPath": str(path),
        }

    def _artifact_bindings(self, descriptor, value, *, after: bool, context):
        private_output = (
            context.get("privateBindings", {}).get("artifacts", {}).get("output")
        )
        output_fields = [
            key for key in ("outputPath", "path") if isinstance(value.get(key), str)
        ]
        if not output_fields and isinstance(private_output, Mapping):
            output_fields.append("carrierReservedOutput")
        input_fields = [
            key
            for key in (
                "inputPath",
                "referencePath",
                "targetPath",
                "templatePath",
                "imagePath",
                "path",
            )
            if isinstance(value.get(key), str)
            and not (key == "path" and "reserved_output" in descriptor.artifact_roles)
        ]
        bindings = []
        input_index = 0
        output_index = 0
        for role in descriptor.artifact_roles:
            if role.startswith("managed_input"):
                if descriptor.action_id == "cutagent.action.edit.from_edl":
                    private = (
                        context.get("privateBindings", {})
                        .get("artifacts", {})
                        .get("input")
                    )
                    required = {
                        "stableId",
                        "resolvedPath",
                        "revision",
                        "contentDigest",
                        "allowedRootId",
                        "reservationIdentity",
                    }
                    if not isinstance(private, Mapping) or not required <= set(private):
                        raise ValidationError(
                            "Prepared EDL import lacks managed artifact custody."
                        )
                    path = Path(private["resolvedPath"])
                    identity = private["reservationIdentity"]
                    stat = path.lstat() if path.exists() else None
                    if (
                        stat is None
                        or path.is_symlink()
                        or not path.is_file()
                        or stat.st_dev != identity.get("device")
                        or stat.st_ino != identity.get("inode")
                    ):
                        raise ValidationError(
                            "Prepared EDL artifact identity changed after admission."
                        )
                    payload = path.read_bytes()
                    if _digest_bytes(payload) != private["contentDigest"]:
                        raise ValidationError(
                            "Prepared EDL artifact bytes changed after admission."
                        )
                    artifact = {
                        key: deepcopy(private[key])
                        for key in (
                            "stableId",
                            "revision",
                            "contentDigest",
                            "allowedRootId",
                        )
                    }
                    artifact.update(
                        digest=private["contentDigest"], resolvedPath=str(path)
                    )
                else:
                    if input_index >= len(input_fields):
                        raise ValidationError(
                            "Residual action omitted a managed input path."
                        )
                    artifact = self._artifact(value[input_fields[input_index]])
                    input_index += 1
                bindings.append({"role": role, **artifact})
            elif role == "reserved_output":
                if output_index >= len(output_fields):
                    raise ValidationError(
                        "Residual action omitted its reserved output path."
                    )
                private = (
                    context.get("privateBindings", {})
                    .get("artifacts", {})
                    .get("output")
                )
                required = {
                    "stableId",
                    "resolvedPath",
                    "revision",
                    "reservationId",
                    "allowedRootId",
                    "pathDigest",
                    "reservationIdentity",
                }
                if not isinstance(private, Mapping) or not required <= set(private):
                    raise ValidationError(
                        "Residual output lacks carrier-owned private reservation custody."
                    )
                path = Path(private["resolvedPath"])
                try:
                    path_stat = path.lstat()
                except OSError as error:
                    raise ValidationError(
                        "Residual carrier output reservation is unavailable."
                    ) from error
                identity = private["reservationIdentity"]
                if (
                    not path.is_absolute()
                    or path.is_symlink()
                    or not path.is_file()
                    or not isinstance(identity, Mapping)
                    or path_stat.st_dev != identity.get("device")
                    or path_stat.st_ino != identity.get("inode")
                ):
                    raise ValidationError(
                        "Residual carrier output reservation identity changed."
                    )
                output_index += 1
                item = {
                    "role": role,
                    **{
                        key: deepcopy(private[key])
                        for key in (
                            "stableId",
                            "revision",
                            "reservationId",
                            "allowedRootId",
                            "pathDigest",
                        )
                    },
                }
                if after:
                    data = path.read_bytes()
                    after_stat = path.lstat()
                    if (
                        after_stat.st_dev != identity.get("device")
                        or after_stat.st_ino != identity.get("inode")
                        or not data
                    ):
                        raise ValidationError(
                            "Residual carrier output changed identity or contains no verified bytes."
                        )
                    item.update(
                        revision=f"revision_{hashlib.sha256((str(path) + _digest_bytes(data)).encode()).hexdigest()[:32]}",
                        contentDigest=_digest_bytes(data),
                        byteCount=len(data),
                    )
                bindings.append(item)
            elif role == "derived_sidecar_output":
                binding = context.get("exactRequestBinding", {})
                source_ids = binding.get("identities", {}).get("targetIds", ())
                source_revisions = binding.get("revisions", {}).get("targets", {})
                if len(source_ids) != 1 or source_ids[0] not in source_revisions:
                    raise ValidationError(
                        "Derived sidecar lacks one exact source target."
                    )
                source_id = source_ids[0]
                item = {
                    "role": role,
                    "stableId": f"artifact_sidecar_{hashlib.sha256(source_id.encode()).hexdigest()[:24]}",
                    "revision": f"revision_{hashlib.sha256((source_id + ':absent').encode()).hexdigest()[:32]}",
                    "sourceArtifactId": source_id,
                    "sourceRevision": source_revisions[source_id],
                    "allowedRootId": "managed_source_sidecars",
                }
                if after:
                    record = self._handler_results.get(context.get("operationId"))
                    raw = (
                        record.get("handlerResult")
                        if isinstance(record, Mapping)
                        else None
                    )
                    data = raw.get("data", raw) if isinstance(raw, Mapping) else None
                    sidecar_path = (
                        data.get("sidecar_path") if isinstance(data, Mapping) else None
                    )
                    if not isinstance(sidecar_path, str):
                        raise ValidationError(
                            "Derived sidecar handler omitted its output path proof."
                        )
                    path, _root = self._managed_path(sidecar_path)
                    if not path.is_file() or path.is_symlink():
                        raise ValidationError(
                            "Derived sidecar output is not a regular managed file."
                        )
                    payload = path.read_bytes()
                    item.update(
                        revision=f"revision_{hashlib.sha256((str(path) + _digest_bytes(payload)).encode()).hexdigest()[:32]}",
                        contentDigest=_digest_bytes(payload),
                        byteCount=len(payload),
                    )
                bindings.append(item)
        return bindings

    def _inspect(self, context, *, action_id=None, value=None, phase="current"):
        timeline = context.get("timeline")
        if not isinstance(timeline, Mapping):
            return None
        if not callable(self._inspector):
            raise ValidationError(
                "Residual action lacks fresh private timeline inspection."
            )
        payload = {
            "projectId": context["project"]["projectId"],
            "timelineId": timeline["timelineId"],
        }
        if action_id in {
            "cutagent.action.edit.ripple_delete",
            "cutagent.action.edit.from_edl",
        } and phase in {
            "after",
            "recovery",
        }:
            expected_name = (
                value["newTimelineName"]
                if action_id.endswith("ripple_delete")
                else value["expectedTimelineName"]
            )
            payload.update(
                operation=(
                    "edit.ripple_delete.result"
                    if action_id.endswith("ripple_delete")
                    else "edit.from_edl.result"
                ),
                expectedTimelineName=expected_name,
            )
        result = self._inspector(payload)
        if not isinstance(result, Mapping) or not isinstance(
            result.get("snapshot"), Mapping
        ):
            raise ValidationError("Residual private inspection returned no snapshot.")
        if action_id == "cutagent.action.edit.from_edl" and phase in {
            "after",
            "recovery",
        }:
            original = result.get("originalSnapshot")
            if not isinstance(original, Mapping):
                raise ValidationError(
                    "EDL import inspection omitted preserved original timeline custody."
                )
            record = self._handler_results.get(context.get("operationId"))
            if isinstance(record, dict):
                record["preservedOriginalSnapshot"] = deepcopy(original)
        return result["snapshot"]

    def _inspect_collection(self, context, operation: str, **payload):
        if not callable(self._inspector):
            raise ValidationError(
                "Residual action lacks fresh private collection inspection."
            )
        timeline = context.get("timeline")
        if not isinstance(timeline, Mapping):
            raise ValidationError(
                "Residual collection inspection lacks a timeline binding."
            )
        result = self._inspector(
            {
                "operation": operation,
                "projectId": context["project"]["projectId"],
                "timelineId": timeline["timelineId"],
                **payload,
            }
        )
        if not isinstance(result, Mapping) or result.get("operation") != operation:
            raise ValidationError(
                "Residual private collection inspection is malformed."
            )
        return result.get("value")

    @staticmethod
    def _marker_source_frame(marker: Mapping[str, Any]) -> int:
        raw = marker.get("sourceFrame", marker.get("source_frame", marker.get("frame")))
        if isinstance(raw, bool):
            raise ValidationError(
                "Residual marker readback omitted its canonical source frame."
            )
        try:
            value = int(raw)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError(
                "Residual marker readback omitted its canonical source frame."
            ) from error
        return value

    @staticmethod
    def _marker_custom_data(marker: Mapping[str, Any]) -> str:
        value = marker.get("customData", marker.get("custom_data"))
        if not isinstance(value, str):
            raise ValidationError(
                "Residual marker readback omitted customData custody."
            )
        return value

    @classmethod
    def _marker_public_state(cls, marker: Mapping[str, Any]) -> dict[str, Any]:
        try:
            duration = int(marker.get("durationFrames", marker.get("duration")))
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError(
                "Residual marker readback omitted a valid duration."
            ) from error
        if duration < 1:
            raise ValidationError("Residual marker readback omitted a valid duration.")
        domain = marker.get("domain", "source")
        if domain not in {"source", "offset"}:
            domain = "source"
        return {
            "frame": cls._marker_source_frame(marker),
            "domain": domain,
            "color": str(marker.get("color") or ""),
            "name": str(marker.get("name") or ""),
            "note": str(marker.get("note") or ""),
            "durationFrames": duration,
            "customData": cls._marker_custom_data(marker),
        }

    @staticmethod
    def _primary_timeline_item_id(context: Mapping[str, Any]) -> str:
        matches = [
            target_id
            for target_id in context.get("exactRequestBinding", {})
            .get("identities", {})
            .get("targetIds", ())
            if isinstance(target_id, str) and target_id.startswith("timeline_item_")
        ]
        if len(matches) != 1:
            raise ValidationError(
                "Residual child action lacks one exact timeline-item identity."
            )
        return matches[0]

    @classmethod
    def _marker_stable_id(cls, timeline_item_id: str, source_frame: int) -> str:
        return (
            "marker_"
            + hashlib.sha256(
                json.dumps(
                    {
                        "timelineItemId": timeline_item_id,
                        "sourceFrame": source_frame,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()[:32]
        )

    @staticmethod
    def _requested_marker_source_frame(
        value: Mapping[str, Any], snapshot: Mapping[str, Any], timeline_item_id: str
    ) -> int:
        raw = value.get("frame")
        if raw is None:
            raw = (
                value.get("clipOrFrame")
                if value.get("maybeData") is None
                else value.get("frameOrData")
            )
        try:
            requested = int(raw)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError(
                "Residual marker request omitted its canonical source frame."
            ) from error
        if "frame" not in value or value.get("frameDomain", "auto") in {
            "source",
            "raw",
        }:
            return requested
        domain = value.get("frameDomain", "auto")
        matches = [
            clip
            for track in snapshot.get("tracks", ())
            for clip in track.get("clips", ())
            if clip.get("id") == timeline_item_id
        ]
        if len(matches) != 1:
            raise ValidationError(
                "Residual marker target is missing or ambiguous in fresh state."
            )
        source_range = matches[0].get("sourceRange")
        if domain == "offset":
            if not isinstance(source_range, Mapping) or not isinstance(
                source_range.get("start"), int
            ):
                raise ValidationError(
                    "Residual marker offset cannot be resolved to a source frame."
                )
            return source_range["start"] + requested
        if domain != "auto":
            raise ValidationError("Residual marker frame domain is invalid.")
        if (
            isinstance(source_range, Mapping)
            and isinstance(source_range.get("start"), int)
            and isinstance(source_range.get("endExclusive"), int)
            and 0 <= requested < source_range["endExclusive"] - source_range["start"]
        ):
            return source_range["start"] + requested
        return requested

    @staticmethod
    def _fusion_reference(reference: Mapping[str, Any]) -> dict[str, Any]:
        required = {"id", "index", "name", "revision", "graphDigest"}
        if (
            not required <= set(reference)
            or not isinstance(reference.get("id"), str)
            or not isinstance(reference.get("index"), int)
            or reference["index"] < 1
            or not isinstance(reference.get("name"), str)
            or not reference["name"]
            or not isinstance(reference.get("revision"), str)
            or not isinstance(reference.get("graphDigest"), str)
        ):
            raise ValidationError(
                "Residual Fusion inspection omitted full reference and graph-revision state."
            )
        return {
            key: deepcopy(reference[key])
            for key in ("id", "index", "name", "revision", "graphDigest")
        }

    @staticmethod
    def _fusion_collection_state(
        references: list[dict[str, Any]],
        *, create_mode: str | None = None,
    ) -> dict[str, Any]:
        state = {
            "references": deepcopy(references),
            "collectionRevision": f"revision_{_digest(references).removeprefix('sha256:')}",
        }
        if create_mode is not None:
            state["createMode"] = create_mode
        return state

    def _live_child_targets(
        self,
        action_id: str,
        context: Mapping[str, Any],
        value: Mapping[str, Any],
        snapshot: Mapping[str, Any],
        phase: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        after = phase in {"after", "recovery"}
        if (
            action_id.startswith("cutagent.action.clip.marker.")
            and action_id != "cutagent.action.clip.marker.list"
        ):
            timeline_item_id = self._primary_timeline_item_id(context)
            clip_name = value.get("clipName") or value.get("clip")
            raw = self._inspect_collection(
                context, "clip.marker.list", input={"name": clip_name}
            )
            markers = (
                raw.get("payload", {}).get("data", {}).get("markers")
                if isinstance(raw, Mapping)
                else None
            )
            if markers is None and isinstance(raw, Mapping):
                markers = raw.get("data", {}).get("markers", raw.get("markers"))
            if markers is None and isinstance(raw, list):
                markers = raw
            if not isinstance(markers, list):
                raise ValidationError(
                    "Residual marker collection readback is unavailable."
                )
            normalized = [
                self._marker_public_state(item)
                for item in markers
                if isinstance(item, Mapping)
            ]
            if len(normalized) != len(markers):
                raise ValidationError(
                    "Residual marker collection contains a malformed row."
                )
            custom_route = action_id == "cutagent.action.clip.marker.delete_custom"
            wanted_custom = (
                value.get("maybeData")
                if value.get("maybeData") is not None
                else value.get("clipOrData")
            )
            wanted_frame = (
                None
                if custom_route
                else self._requested_marker_source_frame(
                    value, snapshot, timeline_item_id
                )
            )
            matches = [
                item
                for item in normalized
                if (
                    item["customData"] == wanted_custom
                    if custom_route
                    else item["frame"] == wanted_frame
                )
            ]
            creating = action_id.endswith("marker.add")
            deleting = action_id in {
                "cutagent.action.clip.marker.delete",
                "cutagent.action.clip.marker.delete_custom",
            }
            if (
                (creating and not after and matches)
                or (creating and after and len(matches) != 1)
                or (deleting and not after and len(matches) != 1)
                or (deleting and after and matches)
                or (not creating and not deleting and len(matches) != 1)
            ):
                raise ValidationError(
                    "Residual marker target did not reconcile to one exact live object."
                )
            if deleting and after:
                binding = context.get("exactRequestBinding", {})
                candidate = next(
                    (
                        target_id
                        for target_id in binding.get("identities", {}).get(
                            "targetIds", ()
                        )
                        if str(target_id).startswith("marker_")
                    ),
                    None,
                )
                if not candidate:
                    raise ValidationError(
                        "Residual deleted marker identity is unavailable."
                    )
                if not custom_route and candidate != self._marker_stable_id(
                    timeline_item_id,
                    self._requested_marker_source_frame(
                        value, snapshot, timeline_item_id
                    ),
                ):
                    raise ValidationError(
                        "Residual deleted marker identity drifted from its canonical source frame."
                    )
                return (
                    [
                        {
                            "kind": "marker",
                            "stableId": candidate,
                            "revision": snapshot["revision"],
                            "existence": "deleted",
                        }
                    ],
                    {
                        "collection": deepcopy(normalized),
                        "markers": [],
                    },
                )
            if creating and not after:
                planned = self._marker_stable_id(timeline_item_id, int(wanted_frame))
                binding = context.get("exactRequestBinding", {})
                if planned not in binding.get("identities", {}).get("targetIds", ()):
                    raise ValidationError(
                        "Residual planned marker identity is not bound to its canonical source frame."
                    )
                return (
                    [
                        {
                            "kind": "marker",
                            "stableId": planned,
                            "revision": binding["revisions"]["targets"][planned],
                            "existence": "planned_absent",
                        }
                    ],
                    {"collection": deepcopy(normalized), "markers": []},
                )
            marker = matches[0]
            stable_id = self._marker_stable_id(timeline_item_id, marker["frame"])
            binding_ids = (
                context.get("exactRequestBinding", {})
                .get("identities", {})
                .get("targetIds", ())
            )
            if stable_id not in binding_ids:
                raise ValidationError("Residual marker identity is stale or ambiguous.")
            return (
                [
                    {
                        "kind": "marker",
                        "stableId": stable_id,
                        "revision": snapshot["revision"],
                        "existence": "existing",
                        "observed": deepcopy(marker),
                    }
                ],
                {"collection": deepcopy(normalized), "markers": [deepcopy(marker)]},
            )
        if (
            action_id.startswith("cutagent.action.clip.fusion.")
            and action_id != "cutagent.action.clip.fusion.list"
        ):
            primary = self._primary_timeline_item_id(context)
            references = self._inspect_collection(
                context,
                "fusion.compositions",
                timelineItemId=primary,
            )
            if not isinstance(references, list):
                raise ValidationError(
                    "Residual Fusion collection readback is unavailable."
                )
            if any(not isinstance(item, Mapping) for item in references):
                raise ValidationError(
                    "Residual Fusion collection contains a malformed reference."
                )
            references = [self._fusion_reference(item) for item in references]
            requested = int(
                value.get("index", value.get("compIndex", value.get("comp", 1)))
            )
            matches = [
                item
                for item in references
                if isinstance(item, Mapping) and item.get("index") == requested
            ]
            creating = action_id in {
                "cutagent.action.clip.fusion.add",
                "cutagent.action.clip.fusion.import",
            }
            deleting = action_id == "cutagent.action.clip.fusion.delete"
            if (
                (deleting and not after and len(matches) != 1)
                or (deleting and after and matches)
                or (not creating and not deleting and len(matches) != 1)
            ):
                raise ValidationError(
                    "Residual Fusion target did not reconcile to one exact live composition."
                )
            if creating:
                before = self._fusion_before_references(
                    context, operation="create"
                )
                create_mode = "append"
                if action_id == "cutagent.action.clip.fusion.import":
                    create_mode = context.get("privateBindings", {}).get(
                        "fusionImportMode", "append"
                    )
                    if create_mode not in {"append", "replace_single_blank_holder"}:
                        raise ValidationError("Residual Fusion import mode is invalid.")
                before_ids = {item["id"] for item in before}
                if len(before) != len(before_ids):
                    raise ValidationError(
                        "Residual Fusion pre-create collection is ambiguous."
                    )
                current_by_id = {
                    item["id"]: item
                    for item in references
                    if isinstance(item, Mapping) and isinstance(item.get("id"), str)
                }
                if not after:
                    if references != before:
                        raise ValidationError(
                            "Residual Fusion collection changed after carrier admission."
                        )
                    planned = next(
                        (
                            target_id
                            for target_id in context.get("exactRequestBinding", {})
                            .get("identities", {})
                            .get("targetIds", ())
                            if str(target_id).startswith("planned_fusion_comp_")
                        ),
                        None,
                    )
                    if not planned:
                        raise ValidationError(
                            "Residual Fusion create lacks planned carrier identity."
                        )
                    return (
                        [
                            {
                                "kind": "fusion_composition",
                                "stableId": planned,
                                "revision": context["exactRequestBinding"]["revisions"][
                                    "targets"
                                ][planned],
                                "existence": "planned_absent",
                            }
                        ],
                        self._fusion_collection_state(references, create_mode=create_mode),
                    )
                if create_mode == "replace_single_blank_holder":
                    replacement = references[0] if len(before) == 1 and len(references) == 1 else None
                    original = before[0] if len(before) == 1 else None
                    if (
                        not replacement or not original
                        or original["index"] != 1 or original["name"] != "Composition 1"
                        or replacement["index"] != 1
                        or replacement["graphDigest"] == original["graphDigest"]
                        or replacement["revision"] == original["revision"]
                    ):
                        raise ValidationError(
                            "Residual Fusion holder import did not replace one exact blank composition."
                        )
                    return (
                        [{
                            "kind": "fusion_composition",
                            "stableId": replacement["id"],
                            "revision": replacement["revision"],
                            "existence": "existing",
                        }],
                        self._fusion_collection_state(references, create_mode=create_mode),
                    )
                created_ids = set(current_by_id) - before_ids
                if (
                    len(created_ids) != 1
                    or before_ids - set(current_by_id)
                    or any(current_by_id[item["id"]] != item for item in before)
                ):
                    raise ValidationError(
                        "Residual Fusion create did not reconcile to one exact new composition."
                    )
                reference = current_by_id[created_ids.pop()]
                return (
                    [
                        {
                            "kind": "fusion_composition",
                            "stableId": reference["id"],
                            "revision": reference.get("revision", snapshot["revision"]),
                            "existence": "existing",
                        }
                    ],
                    self._fusion_collection_state(references, create_mode=create_mode),
                )
            if deleting and not after:
                before = self._fusion_before_references(
                    context, operation="delete"
                )
                if references != before:
                    raise ValidationError(
                        "Residual Fusion collection changed after carrier admission."
                    )
            if deleting and after:
                binding = context.get("exactRequestBinding", {})
                before = self._fusion_before_references(
                    context, operation="delete"
                )
                candidates = [item for item in before if item["index"] == requested]
                if len(candidates) != 1:
                    raise ValidationError(
                        "Residual deleted Fusion identity is unavailable or ambiguous."
                    )
                candidate = candidates[0]["id"]
                expected_after = [item for item in before if item["id"] != candidate]
                if references != expected_after:
                    raise ValidationError(
                        "Residual Fusion delete changed a non-target composition reference or graph revision."
                    )
                if candidate not in binding.get("identities", {}).get("targetIds", ()):
                    raise ValidationError(
                        "Residual deleted Fusion identity is unavailable."
                    )
                return (
                    [
                        {
                            "kind": "fusion_composition",
                            "stableId": candidate,
                            "revision": snapshot["revision"],
                            "existence": "deleted",
                        }
                    ],
                    self._fusion_collection_state(references),
                )
            reference = matches[0]
            stable_id = reference.get("id")
            if not isinstance(stable_id, str) or not stable_id:
                raise ValidationError(
                    "Residual Fusion composition lacks stable live identity."
                )
            if stable_id not in context.get("exactRequestBinding", {}).get(
                "identities", {}
            ).get("targetIds", ()):
                raise ValidationError("Residual Fusion composition identity is stale.")
            return (
                [
                    {
                        "kind": "fusion_composition",
                        "stableId": stable_id,
                        "revision": reference["revision"],
                        "existence": "existing",
                    }
                ],
                self._fusion_collection_state(references),
            )
        if action_id.startswith("cutagent.action.text.insert"):
            if not after:
                return ([], None)
            record = self._handler_results.get(context.get("operationId"), {})
            before_ids = (
                set(record.get("beforeTimelineItemIds", ()))
                if isinstance(record, Mapping)
                else set()
            )
            current = [
                (track, clip)
                for track in snapshot.get("tracks", ())
                for clip in track.get("clips", ())
                if isinstance(clip.get("id"), str) and clip["id"] not in before_ids
            ]
            expected = (
                len(value.get("items", ()))
                if action_id.endswith("template_batch")
                else 1
            )
            if len(current) != expected:
                raise ValidationError(
                    "Residual text creation did not reconcile to the exact new live items."
                )
            return (
                [
                    {
                        "kind": "timeline_item",
                        "stableId": clip["id"],
                        "revision": snapshot["revision"],
                        "projectId": snapshot["project"]["id"],
                        "timelineId": snapshot["timeline"]["id"],
                        "snapshotTimelineItemId": clip["snapshotId"],
                        "trackType": track["type"],
                        "trackIndex": track["index"],
                        "linkedTimelineItemIds": clip.get("linkedItemIds") or [],
                        "recordRange": deepcopy(clip.get("recordRange")),
                        "existence": "existing",
                    }
                    for track, clip in current
                ],
                None,
            )
        if action_id == "cutagent.action.edit.camera_pip":
            if not after:
                return ([], None)
            record = self._handler_results.get(context.get("operationId"), {})
            before_ids = (
                set(record.get("beforeTimelineItemIds", ()))
                if isinstance(record, Mapping)
                else set()
            )
            current = [
                (track, clip)
                for track in snapshot.get("tracks", ())
                for clip in track.get("clips", ())
                if isinstance(clip.get("id"), str)
                and clip["id"] not in before_ids
                and track.get("type") == "video"
            ]
            if len(current) != 2:
                raise ValidationError(
                    "Camera PiP did not reconcile to two exact new timeline items."
                )
            return (
                [
                    {
                        "kind": "timeline_item",
                        "stableId": clip["id"],
                        "revision": snapshot["revision"],
                        "projectId": snapshot["project"]["id"],
                        "timelineId": snapshot["timeline"]["id"],
                        "snapshotTimelineItemId": clip["snapshotId"],
                        "trackType": track["type"],
                        "trackIndex": track["index"],
                        "linkedTimelineItemIds": clip.get("linkedItemIds") or [],
                        "recordRange": deepcopy(clip.get("recordRange")),
                        "existence": "existing",
                    }
                    for track, clip in current
                ],
                None,
            )
        return ([], None)

    @staticmethod
    def _timeline_target(snapshot, stable_id, revision):
        matches = [
            (track, clip)
            for track in snapshot.get("tracks", ())
            for clip in track.get("clips", ())
            if clip.get("id") == stable_id
        ]
        if len(matches) != 1:
            return None
        track, clip = matches[0]
        return {
            "kind": "timeline_item",
            "stableId": stable_id,
            "revision": revision,
            "projectId": snapshot["project"]["id"],
            "timelineId": snapshot["timeline"]["id"],
            "snapshotTimelineItemId": clip["snapshotId"],
            "trackType": track["type"],
            "trackIndex": track["index"],
            "linkedTimelineItemIds": clip.get("linkedItemIds") or [],
            "recordRange": deepcopy(clip.get("recordRange")),
        }

    @staticmethod
    def _public_timeline_targets(
        snapshot: Mapping[str, Any], target_ids: set[str]
    ) -> list[dict[str, Any]]:
        def public_range(value: Any, domain: str) -> dict[str, Any] | None:
            if value is None and domain == "source_range":
                return None
            if not isinstance(value, Mapping) \
                    or not isinstance(value.get("start"), int) \
                    or not isinstance(value.get("endExclusive"), int) \
                    or value["endExclusive"] <= value["start"]:
                raise ValidationError(
                    "Residual public target omitted a valid frame range."
                )
            return {
                "domain": domain,
                "unit": "frames",
                "start": value["start"],
                "endExclusive": value["endExclusive"],
            }

        rows = []
        for track in snapshot.get("tracks", ()):
            clips = track.get("clips", ())
            for clip in clips:
                if clip.get("id") not in target_ids:
                    continue
                record_range = public_range(
                    clip.get("recordRange"), "timeline_record_range"
                )
                neighbors = []
                for other in clips:
                    if (
                        other is clip
                        or not isinstance(other.get("id"), str)
                        or not isinstance(other.get("recordRange"), Mapping)
                    ):
                        continue
                    other_range = other["recordRange"]
                    if other_range.get("endExclusive") == record_range.get("start"):
                        relationship = "previous"
                    elif other_range.get("start") == record_range.get("endExclusive"):
                        relationship = "next"
                    elif other_range.get("start", 0) < record_range.get(
                        "endExclusive", 0
                    ) and record_range.get("start", 0) < other_range.get(
                        "endExclusive", 0
                    ):
                        relationship = "overlapping"
                    else:
                        continue
                    neighbors.append(
                        {
                            "timelineItemId": other["id"],
                            "relationship": relationship,
                            "recordRange": public_range(
                                other_range, "timeline_record_range"
                            ),
                        }
                    )
                rows.append(
                    {
                        "projectId": snapshot.get("project", {}).get("id"),
                        "timelineId": snapshot.get("timeline", {}).get(
                            "id", snapshot.get("timelineId")
                        ),
                        "timelineItemId": clip["id"],
                        "snapshotTimelineItemId": clip.get("snapshotId"),
                        "name": clip.get("name"),
                        "track": {
                            "type": track.get("type"),
                            "index": track.get("index"),
                        },
                        "recordRange": record_range,
                        "sourceRange": public_range(
                            clip.get("sourceRange"), "source_range"
                        ),
                        "linkedTimelineItemIds": deepcopy(
                            clip.get("linkedItemIds") or []
                        ),
                        "protectedNeighbors": neighbors[:16],
                    }
                )
        if len(rows) != len(target_ids):
            raise ValidationError(
                "Residual public target set is missing or ambiguous in fresh readback."
            )
        return rows

    @staticmethod
    def _independent_evidence(descriptor, targets, value):
        modalities = set(descriptor.verification)
        needs_frame = "rendered_frame" in modalities
        if not needs_frame:
            return {}
        timeline_targets = [
            target for target in targets if target.get("kind") == "timeline_item"
        ]
        ranges = [target.get("recordRange") for target in timeline_targets]
        ranges = [
            item
            for item in ranges
            if isinstance(item, Mapping)
            and isinstance(item.get("start"), int)
            and isinstance(item.get("endExclusive"), int)
            and item["endExclusive"] > item["start"]
        ]
        if not ranges:
            raise ValidationError(
                "Residual terminal media proof lacks an exact target range."
            )
        from ..commands import clip
        from ..core import clip_ops, timeline_ops

        connection = clip.get_connection(require_timeline=True)
        directory = Path(tempfile.mkdtemp(prefix="cutagent-residual-proof-"))
        proof = {}
        original = timeline_ops.get_playhead(connection)
        try:
            start = min(item["start"] for item in ranges)
            if needs_frame:
                try:
                    timeline_origin = int(connection.timeline.GetStartFrame())
                except Exception:
                    timeline_origin = int(getattr(connection, "start_frame", 0) or 0)
                relative_start = start - timeline_origin
                if relative_start < 0:
                    raise ValidationError(
                        "Residual rendered proof target precedes the timeline origin."
                    )
                positioned = timeline_ops.set_playhead(
                    connection,
                    f"{relative_start}f",
                    return_details=True,
                    frame_tolerance=0,
                )
                if int(positioned.get("final_frame")) != start:
                    raise ValidationError(
                        "Residual rendered proof could not settle on the exact target frame."
                    )
                frame_path = directory / "proof.png"
                exported = clip_ops.export_current_frame_as_still(
                    connection, str(frame_path)
                )
                if (
                    exported.get("exported") is not True
                    or not frame_path.is_file()
                    or frame_path.stat().st_size < 1
                ):
                    raise ValidationError(
                        "Residual rendered proof did not produce an exact frame."
                    )
                proof["rendered"] = {
                    "digest": _digest_bytes(frame_path.read_bytes()),
                    "summary": "Fresh target frame was rendered after the mutation.",
                }
            return proof
        finally:
            try:
                timecode = (
                    original.get("timecode") if isinstance(original, Mapping) else None
                )
                if timecode:
                    timeline_ops.set_playhead(
                        connection,
                        str(timecode),
                        return_details=True,
                        frame_tolerance=0,
                    )
            finally:
                shutil.rmtree(directory, ignore_errors=True)

    @staticmethod
    def _verified_semantic_state(action_id, value, targets, record, action_state):
        if action_id in _SINGLE_RESULT_VALIDATION_ACTIONS:
            raw = record.get("handlerResult") if isinstance(record, Mapping) else None
            handler_input = record.get("handlerInput") \
                if isinstance(record, Mapping) else None
            data = raw.get("data", raw) if isinstance(raw, Mapping) else None
            required = {
                "cutagent.action.audio.beat_detect": {"input", "beats"},
                "cutagent.action.audio.waveform_offset": {
                    "offset_seconds", "offset_frames_float", "confidence",
                },
                "cutagent.action.clip.offset": {
                    "clip", "left_offset", "right_offset",
                },
            }[action_id]
            if not isinstance(data, Mapping) or not required <= set(data):
                raise ValidationError("Residual read result is malformed.")
            if not isinstance(handler_input, Mapping):
                raise ValidationError("Residual read result lacks its admitted input.")
            if action_id == "cutagent.action.audio.beat_detect" and data[
                "input"
            ] != handler_input.get("inputPath"):
                raise ValidationError("Residual beat result does not match its input.")
            if action_id == "cutagent.action.clip.offset" \
                    and data["clip"] != handler_input.get("clipName"):
                raise ValidationError("Residual clip offset result does not match its input.")
            return {"kind": "validated_result"}
        if action_id.startswith("cutagent.action.clip.marker."):
            before_state = (
                record.get("beforeActionState") if isinstance(record, Mapping) else None
            )
            before_collection = (
                before_state.get("collection")
                if isinstance(before_state, Mapping)
                else None
            )
            after_collection = (
                action_state.get("collection")
                if isinstance(action_state, Mapping)
                else None
            )
            if not isinstance(before_collection, list) or not isinstance(
                after_collection, list
            ):
                raise ValidationError(
                    "Residual marker verification lacks full before/after collection custody."
                )
            markers = [target for target in targets if target.get("kind") == "marker"]
            if len(markers) != 1:
                raise ValidationError(
                    "Residual marker verification lacks one exact live target."
                )
            marker = markers[0]
            deleting = action_id in {
                "cutagent.action.clip.marker.delete",
                "cutagent.action.clip.marker.delete_custom",
            }
            if marker.get("existence") != ("deleted" if deleting else "existing"):
                raise ValidationError(
                    "Residual marker post-state did not match the requested existence."
                )
            observed = marker.get("observed")
            if not deleting:
                if not isinstance(observed, Mapping):
                    raise ValidationError(
                        "Residual marker verification lacks exact marker fields."
                    )
                if action_id.endswith("marker.add"):
                    expected = {
                        "color": value.get("color", "Blue"),
                        "name": value.get("markerName", ""),
                        "note": value.get("note", ""),
                        "durationFrames": value.get("duration", 1),
                        "customData": "",
                    }
                    for key, expected_value in expected.items():
                        if (
                            expected_value is not None
                            and observed.get(key) != expected_value
                        ):
                            raise ValidationError(
                                f"Residual marker add readback mismatched {key}."
                            )
                elif action_id.endswith("marker.custom_data"):
                    expected_data = (
                        value.get("maybeData")
                        if value.get("maybeData") is not None
                        else value.get("frameOrData")
                    )
                    if observed.get("customData") != expected_data:
                        raise ValidationError(
                            "Residual marker custom-data readback mismatched the request."
                        )
            expected_collection = deepcopy(before_collection)
            if action_id.endswith("marker.add"):
                expected_collection.append(deepcopy(observed))
            else:
                before_selected = before_state.get("markers")
                if not isinstance(before_selected, list) or len(before_selected) != 1:
                    raise ValidationError(
                        "Residual marker transition lacks one exact selected pre-state marker."
                    )
                matched = [
                    index
                    for index, item in enumerate(expected_collection)
                    if item == before_selected[0]
                ]
                if len(matched) != 1:
                    raise ValidationError(
                        "Residual marker transition lacks one exact pre-state target."
                    )
                index = matched[0]
                if action_id.endswith("marker.custom_data"):
                    expected_collection[index] = {
                        **expected_collection[index],
                        "customData": observed["customData"],
                    }
                else:
                    expected_collection.pop(index)
            def canonical_rows(rows):
                return sorted(
                    json.dumps(item, sort_keys=True, separators=(",", ":"))
                    for item in rows
                )
            if canonical_rows(after_collection) != canonical_rows(expected_collection):
                raise ValidationError(
                    "Residual marker mutation changed an unrelated marker or mismatched the exact target transition."
                )
            return {"kind": "marker", "digest": _digest(marker)}
        if action_id.startswith("cutagent.action.burnin."):
            raw = record.get("handlerResult") if isinstance(record, Mapping) else None
            data = raw.get("data", raw) if isinstance(raw, Mapping) else None
            before_state = record.get("beforeActionState") if isinstance(record, Mapping) else None
            before_names = before_state.get("presetNames") if isinstance(before_state, Mapping) else None
            after_names = action_state.get("presetNames") if isinstance(action_state, Mapping) else None
            if not isinstance(data, Mapping) or not isinstance(before_names, list) or not isinstance(after_names, list) \
                    or len(before_names) != len(set(before_names)) or len(after_names) != len(set(after_names)):
                raise ValidationError("Burn-in verification lacks authoritative preset-catalog custody.")
            preset_name = data.get("name")
            if not isinstance(preset_name, str) or not preset_name or preset_name not in after_names:
                raise ValidationError("Burn-in verification could not resolve one exact preset identity.")
            if action_id == "cutagent.action.burnin.preset.import":
                if data.get("imported") is not True or set(after_names) - set(before_names) != {preset_name}:
                    raise ValidationError("Burn-in import did not produce one exact catalog addition.")
            elif action_id == "cutagent.action.burnin.preset.export":
                outputs = [target for target in targets if target.get("kind") == "managed_artifact"]
                if data.get("exported") is not True or before_names != after_names or len(outputs) != 1:
                    raise ValidationError("Burn-in export lacks exact artifact and catalog readback.")
            elif data.get("loaded") is not True or before_names != after_names:
                raise ValidationError("Burn-in load lacks exact stable-catalog readback.")
            return {
                "kind": "burnin_preset", "presetName": preset_name,
                "catalogDigest": _digest(after_names),
            }
        if action_id in {"cutagent.action.clip.fusion.add", "cutagent.action.clip.fusion.delete"}:
            rows = [target for target in targets if target.get("kind") == "fusion_composition"]
            expected = "existing" if action_id.endswith(".add") else "deleted"
            if len(rows) != 1 or rows[0].get("existence") != expected:
                raise ValidationError(
                    "Residual Fusion post-state did not match the requested existence."
                )
            return {"kind": "fusion_composition", "digest": _digest(rows[0])}
        if action_id.startswith("cutagent.action.edit."):
            native_transition_state = None
            before_snapshot = (
                record.get("beforeSnapshot") if isinstance(record, Mapping) else None
            )
            after_snapshot = (
                record.get("afterSnapshot") if isinstance(record, Mapping) else None
            )
            if not isinstance(before_snapshot, Mapping) or not isinstance(
                after_snapshot, Mapping
            ):
                raise ValidationError(
                    "Edit verification lacks complete before/after snapshot custody."
                )
            if action_id == "cutagent.action.edit.transition.add":
                raw = record.get("handlerResult") if isinstance(record, Mapping) else None
                data = raw.get("data", raw) if isinstance(raw, Mapping) else None
                verification = data.get("verification") if isinstance(data, Mapping) else None
                inserted = data.get("inserted") if isinstance(data, Mapping) else None
                checks = verification.get("checks") if isinstance(verification, Mapping) else None
                identities_match = isinstance(inserted, list) and isinstance(checks, list) and all(
                    isinstance(row, Mapping)
                    and isinstance(check, Mapping)
                    and isinstance(row.get("item_id"), str)
                    and bool(row["item_id"])
                    and check.get("expected_item_id") == row["item_id"]
                    and check.get("observed_item_id") == row["item_id"]
                    for row, check in zip(inserted, checks)
                )
                if not isinstance(inserted, list) or not inserted \
                        or not isinstance(checks, list) or len(checks) != len(inserted) \
                        or verification.get("status") != "verified" \
                        or verification.get("inserted_count") != len(inserted) \
                        or not identities_match \
                        or any(not isinstance(check, Mapping) or check.get("ok") is not True for check in checks):
                    raise ValidationError(
                        "Transition mutation lacks verified native transition-item readback."
                    )
                expected_start = (
                    value["editFrame"]
                    if value["placement"] == "start"
                    else value["editFrame"] - value["durationFrames"]
                    if value["placement"] == "end"
                    else value["editFrame"] - (value["durationFrames"] // 2)
                )
                primary_track_index = value["outgoing"]["trackIndex"]
                video_rows = [row for row in inserted if row.get("track_type") == "video"]
                audio_rows = [row for row in inserted if row.get("track_type") == "audio"]
                expected_audio_count = (
                    1
                    if value["scope"] == "audio"
                    or (value["scope"] == "linked" and value["linkedAudioTargets"])
                    else 0
                )
                expected_audio_track_index = (
                    primary_track_index
                    if value["scope"] == "audio"
                    else (
                        value["linkedAudioTargets"][0]["trackIndex"]
                        if expected_audio_count
                        else None
                    )
                )
                if len(video_rows) != (0 if value["scope"] == "audio" else 1) \
                        or len(audio_rows) != expected_audio_count \
                        or len(video_rows) + len(audio_rows) != len(inserted) \
                        or any(row.get("start") != expected_start or row.get("duration") != value["durationFrames"] for row in inserted) \
                        or any(row.get("track_index") != primary_track_index for row in video_rows) \
                        or any(row.get("track_index") != expected_audio_track_index for row in audio_rows):
                    raise ValidationError(
                        "Transition native readback drifted from the exact requested seam, range, or track."
                    )
                native_transition_state = {
                    "inserted": deepcopy(inserted),
                    "verification": deepcopy(dict(verification)),
                }
            elif action_id == "cutagent.action.edit.transition.batch":
                raw = record.get("handlerResult") if isinstance(record, Mapping) else None
                data = raw.get("data", raw) if isinstance(raw, Mapping) else None
                verification = data.get("verification") if isinstance(data, Mapping) else None
                inserted = data.get("inserted") if isinstance(data, Mapping) else None
                results = data.get("results") if isinstance(data, Mapping) else None
                requested = value.get("transitions")
                requested = requested if isinstance(requested, list) else [requested]
                checks = verification.get("checks") if isinstance(verification, Mapping) else None
                checks = checks if isinstance(checks, list) else []
                check_ids = {
                    check.get("observed_item_id")
                    for check in checks
                    if isinstance(check, Mapping)
                    and check.get("ok") is True
                    and check.get("expected_item_id") == check.get("observed_item_id")
                }
                if (
                    not isinstance(inserted, list)
                    or not isinstance(results, list)
                    or len(results) != len(requested)
                    or not isinstance(verification, Mapping)
                    or verification.get("status") != "verified"
                    or any(
                        not isinstance(row, Mapping)
                        or not isinstance(row.get("index"), int)
                        for row in results
                    )
                    or sorted(row["index"] for row in results)
                    != list(range(len(requested)))
                ):
                    raise ValidationError(
                        "Transition batch lacks complete verified per-seam readback."
                    )
                observed_inserted = []
                verified_results = []
                for index, transition in enumerate(requested):
                    result_rows = [
                        row for row in results
                        if isinstance(row, Mapping) and row.get("index") == index
                    ]
                    if len(result_rows) != 1 or not isinstance(transition, Mapping):
                        raise ValidationError(
                            "Transition batch lacks complete verified per-seam readback."
                        )
                    result_row = result_rows[0]
                    inserted_rows = result_row.get("inserted") or []
                    skipped_rows = result_row.get("skipped_existing") or []
                    if (
                        result_row.get("ok") is not True
                        or not isinstance(inserted_rows, list)
                        or not isinstance(skipped_rows, list)
                        or bool(inserted_rows) == bool(skipped_rows)
                    ):
                        raise ValidationError(
                            "Transition batch result is neither one verified insertion nor an idempotent skip."
                        )
                    expected_start = (
                        transition["editFrame"]
                        if transition["placement"] == "start"
                        else transition["editFrame"] - transition["durationFrames"]
                        if transition["placement"] == "end"
                        else transition["editFrame"] - (transition["durationFrames"] // 2)
                    )
                    observed_rows = inserted_rows or skipped_rows
                    if len(observed_rows) != 1 or any(
                        not isinstance(row, Mapping)
                        or row.get("track_type") != "video"
                        or row.get("track_index") != transition["outgoing"]["trackIndex"]
                        or row.get("start") != expected_start
                        or row.get("duration") != transition["durationFrames"]
                        for row in observed_rows
                    ):
                        raise ValidationError(
                            "Transition batch readback drifted from a requested seam, duration, or track."
                        )
                    if inserted_rows and any(
                        not isinstance(row.get("item_id"), str)
                        or not row["item_id"]
                        or row["item_id"] not in check_ids
                        for row in inserted_rows
                    ):
                        raise ValidationError(
                            "Transition batch insertion lacks exact native item identity readback."
                        )
                    observed_inserted.extend(inserted_rows)
                    verified_results.append(deepcopy(dict(result_row)))
                if observed_inserted != inserted:
                    raise ValidationError(
                        "Transition batch aggregate readback drifted from its per-seam results."
                    )
                native_transition_state = {
                    "inserted": deepcopy(inserted),
                    "results": verified_results,
                    "verification": deepcopy(dict(verification)),
                    "noOp": not inserted,
                }
            if action_id == "cutagent.action.edit.from_edl":
                preserved = record.get("preservedOriginalSnapshot")
                if preserved != before_snapshot:
                    raise ValidationError(
                        "EDL import changed the original timeline while creating its new timeline."
                    )
                if (
                    after_snapshot.get("timeline", {}).get("id")
                    == before_snapshot.get("timeline", {}).get("id")
                    or after_snapshot.get("timeline", {}).get("name")
                    != value["expectedTimelineName"]
                ):
                    raise ValidationError(
                        "EDL import did not reconcile to the exact expected new timeline."
                    )
            elif before_snapshot.get("revision") == after_snapshot.get("revision") and not (
                action_id == "cutagent.action.edit.transition.batch"
                and isinstance(native_transition_state, Mapping)
                and native_transition_state.get("noOp") is True
            ):
                raise ValidationError(
                    "Edit mutation did not advance the exact timeline revision."
                )
            if action_id == "cutagent.action.edit.transition.batch":
                before_items = _stable_ordinary_timeline_items(before_snapshot)
                after_items = _stable_ordinary_timeline_items(after_snapshot)
            else:
                before_items = {
                    clip["id"]: (track, clip)
                    for track in before_snapshot.get("tracks", ())
                    for clip in track.get("clips", ())
                    if isinstance(clip.get("id"), str)
                }
                after_items = {
                    clip["id"]: (track, clip)
                    for track in after_snapshot.get("tracks", ())
                    for clip in track.get("clips", ())
                    if isinstance(clip.get("id"), str)
                }
            removed = sorted(set(before_items) - set(after_items))
            created = sorted(set(after_items) - set(before_items))
            changed = sorted(
                item_id
                for item_id in set(before_items) & set(after_items)
                if before_items[item_id] != after_items[item_id]
            )
            if action_id == "cutagent.action.edit.transition.batch":
                unmatched_created = set(created)
                matched_transition_ids = set()
                for row in native_transition_state.get("inserted", ()):
                    start = row.get("start")
                    duration = row.get("duration")
                    pretty_type = row.get("pretty_type")
                    matches = []
                    for item_id in unmatched_created:
                        track, clip = after_items[item_id]
                        record_range = clip.get("recordRange")
                        if not isinstance(record_range, Mapping):
                            continue
                        if (
                            track.get("type") == row.get("track_type")
                            and track.get("index") == row.get("track_index")
                            and record_range.get("start") == start
                            and record_range.get("endExclusive") == start + duration
                            and (
                                not isinstance(pretty_type, str)
                                or clip.get("name") == pretty_type
                            )
                        ):
                            matches.append(item_id)
                    if len(matches) != 1:
                        raise ValidationError(
                            "Transition batch could not reconcile one exact projected transition item.",
                            details={
                                "native_item_id": row.get("item_id"),
                                "projected_matches": sorted(matches),
                            },
                        )
                    matched_transition_ids.add(matches[0])
                    unmatched_created.remove(matches[0])
                created = [
                    item_id for item_id in created
                    if item_id not in matched_transition_ids
                ]
                if removed or created or changed:
                    raise ValidationError(
                        "Transition batch changed an unrelated ordinary timeline item.",
                        details={
                            "removed_item_ids": removed,
                            "created_item_ids": created,
                            "changed_item_ids": changed,
                        },
                    )
            if action_id == "cutagent.action.edit.from_edl":
                removed = []
                changed = []
                created = sorted(after_items)
                if not created:
                    raise ValidationError(
                        "EDL import produced no independently readable imported items."
                    )
            elif not (removed or created or changed) and native_transition_state is None:
                raise ValidationError(
                    "Edit mutation produced no independently observable semantic change."
                )
            requested = {
                item["id"]
                for item in (
                    [
                        value.get("target"),
                        value.get("outgoing"),
                        value.get("incoming"),
                        value.get("leftNeighbor"),
                        value.get("rightNeighbor"),
                    ]
                    + list(value.get("targets", ()))
                    + list(value.get("sourceTargets", ()))
                    + list(value.get("sourceAudioTargets", ()))
                    + list(value.get("linkedAudioTargets", ()))
                    + [
                        item
                        for transition in (
                            value.get("transitions")
                            if isinstance(value.get("transitions"), list)
                            else [value.get("transitions")]
                        )
                        if isinstance(transition, Mapping)
                        for item in (transition.get("outgoing"), transition.get("incoming"))
                    ]
                )
                if isinstance(item, Mapping) and isinstance(item.get("id"), str)
            }
            if requested and not requested <= set(before_items):
                raise ValidationError(
                    "Edit mutation request was not bound to every exact pre-state item."
                )
            if action_id == "cutagent.action.edit.ripple_delete":
                start, end = value["rangeStartFrame"], value["rangeEndFrameExclusive"]
                shift = end - start
                requested = {item["id"] for item in value["targets"]}
                for item_id, (track, clip) in before_items.items():
                    if item_id in requested:
                        continue
                    record = clip.get("recordRange", {})
                    expected_start = (
                        record.get("start") - shift
                        if record.get("start", 0) >= end
                        else record.get("start")
                    )
                    expected_end = (
                        record.get("endExclusive") - shift
                        if record.get("start", 0) >= end
                        else record.get("endExclusive")
                    )
                    matches = [
                        candidate
                        for after_track, candidate in after_items.values()
                        if after_track.get("type") == track.get("type")
                        and after_track.get("index") == track.get("index")
                        and candidate.get("name") == clip.get("name")
                        and candidate.get("sourceRange") == clip.get("sourceRange")
                        and candidate.get("recordRange", {}).get("start")
                        == expected_start
                        and candidate.get("recordRange", {}).get("endExclusive")
                        == expected_end
                    ]
                    if len(matches) != 1:
                        raise ValidationError(
                            "Ripple-delete readback did not preserve and shift each unaffected item exactly."
                        )
                removed = sorted(requested)
            return {
                "kind": "edit_snapshot_transition",
                "digest": _digest(
                    {
                        "removed": removed, "created": created, "changed": changed,
                        "nativeTransition": native_transition_state,
                    }
                ),
                "removedItemIds": removed,
                "createdItemIds": created,
                "changedItemIds": changed,
                "requestedItemIds": sorted(requested),
                "beforeSnapshot": deepcopy(before_snapshot),
                "afterSnapshot": deepcopy(after_snapshot),
                **({"nativeTransition": native_transition_state} if native_transition_state else {}),
            }
        raise ValidationError(
            "Residual route has no action-specific production verifier."
        )

    def _resolve(self, action_id, context, value, *, phase):
        descriptor = _DESCRIPTORS[action_id]
        binding = context.get("exactRequestBinding", {})
        identities = binding.get("identities", {})
        revisions = binding.get("revisions", {})
        target_revisions = revisions.get("targets", {})
        snapshot = self._inspect(context, action_id=action_id, value=value, phase=phase)
        after = phase in {"after", "recovery"}
        artifacts = self._artifact_bindings(
            descriptor, value, after=after, context=context
        )
        targets = [
            {
                "kind": "managed_artifact",
                "stableId": item["stableId"],
                "revision": item["revision"],
            }
            for item in artifacts
        ]
        artifact_ids = {item["stableId"] for item in artifacts}
        live_children, action_state = self._live_child_targets(
            action_id, context, value, snapshot, phase
        )
        child_action = (
            action_id.startswith("cutagent.action.clip.marker.")
            or action_id.startswith("cutagent.action.clip.fusion.")
            or action_id.startswith("cutagent.action.text.insert")
            or action_id == "cutagent.action.edit.camera_pip"
        )
        for stable_id in identities.get("targetIds", ()):
            if stable_id in artifact_ids:
                continue
            revision = target_revisions.get(stable_id)
            if not isinstance(revision, str):
                raise ValidationError("Residual carrier target revision is incomplete.")
            item = (
                self._timeline_target(snapshot, stable_id, revision)
                if snapshot
                else None
            )
            if item:
                targets.append(item)
            elif stable_id == identities.get("projectId"):
                targets.append(
                    {"kind": "project", "stableId": stable_id, "revision": revision}
                )
            elif stable_id == identities.get("timelineId"):
                targets.append(
                    {"kind": "timeline", "stableId": stable_id, "revision": revision}
                )
            elif stable_id.startswith("media_pool_item_"):
                targets.append(
                    {
                        "kind": "media_pool_item",
                        "stableId": stable_id,
                        "revision": revision,
                    }
                )
            elif child_action:
                continue
            elif (
                action_id in {
                    "cutagent.action.edit.ripple_delete",
                    "cutagent.action.edit.from_edl",
                }
                and stable_id.startswith("planned_timeline_")
            ):
                continue
            elif (
                action_id.startswith("cutagent.action.edit.")
                and after
                and stable_id.startswith("timeline_item_")
            ):
                targets.append(
                    {
                        "kind": "timeline_item",
                        "stableId": stable_id,
                        "revision": snapshot["revision"],
                        "projectId": identities["projectId"],
                        "timelineId": identities["timelineId"],
                        "snapshotTimelineItemId": f"snapshot_{stable_id}",
                        "trackType": "video",
                        "trackIndex": 1,
                        "linkedTimelineItemIds": [],
                        "existence": "deleted",
                    }
                )
            elif action_id.startswith("cutagent.action.clip.marker."):
                targets.append(
                    {
                        "kind": "marker",
                        "stableId": stable_id,
                        "revision": revision,
                        "existence": "planned_absent"
                        if action_id.endswith("marker.add")
                        else "existing",
                    }
                )
            elif action_id.startswith("cutagent.action.clip.fusion."):
                targets.append(
                    {
                        "kind": "fusion_composition",
                        "stableId": stable_id,
                        "revision": revision,
                        "existence": "planned_absent"
                        if action_id
                        in {
                            "cutagent.action.clip.fusion.add",
                            "cutagent.action.clip.fusion.import",
                        }
                        else "existing",
                    }
                )
            elif action_id.startswith("cutagent.action.text.insert"):
                targets.append(
                    {
                        "kind": "timeline_item",
                        "stableId": stable_id,
                        "revision": revision,
                        "projectId": identities["projectId"],
                        "timelineId": identities["timelineId"],
                        "snapshotTimelineItemId": f"snapshot_{stable_id}",
                        "trackType": "video",
                        "trackIndex": int(value.get("videoTrackIndex", 1)),
                        "linkedTimelineItemIds": [],
                        "existence": "planned_absent" if not after else "existing",
                    }
                )
            else:
                raise ValidationError(
                    "Residual exact target is absent from fresh authority readback."
                )
        targets.extend(live_children)
        if action_id in {
            "cutagent.action.edit.ripple_delete",
            "cutagent.action.edit.from_edl",
        } and after:
            targets.append(
                {
                    "kind": "timeline",
                    "stableId": snapshot["timeline"]["id"],
                    "revision": snapshot["revision"],
                }
            )
        protected = {}
        exact_target_ids = {
            target["stableId"]
            for target in targets
            if target.get("kind") == "timeline_item"
        }
        if descriptor.topology_policy != "not_applicable":
            protected["linkedAvTopology"] = _linked_topology(snapshot)
        if (
            descriptor.topology_policy
            == "mutate_declared_edges_preserve_unrelated_topology"
        ):
            protected["unrelatedLinkedAvTopology"] = _linked_topology(
                snapshot, exact_target_ids
            )
        if descriptor.inspector_preservation != "not_applicable":
            protected["unrelatedInspectorState"] = _unrelated_inspector_state(
                snapshot, exact_target_ids
            )
        pre_state: dict[str, Any] = {"captured": True}
        if action_state is not None:
            pre_state["actionState"] = action_state
        if descriptor.operation_class == "mutation":
            pre_state["semanticState"] = {
                "actionId": action_id,
                "snapshotDigest": _digest(snapshot),
                "snapshotRevision": snapshot.get("revision"),
                "timelineItemIds": [
                    clip["id"]
                    for track in snapshot.get("tracks", ())
                    for clip in track.get("clips", ())
                    if isinstance(clip.get("id"), str)
                ],
                **(
                    {"snapshot": deepcopy(snapshot)}
                    if action_id.startswith("cutagent.action.edit.")
                    else {}
                ),
            }
            existing_item_ids = {
                target["stableId"]
                for target in targets
                if target.get("kind") == "timeline_item"
                and target.get("existence") != "deleted"
            }
            pre_state["publicTargets"] = self._public_timeline_targets(
                snapshot, existing_item_ids
            )
        if action_id.startswith("cutagent.action.burnin."):
            from ..core import render_engine

            preset_names = sorted({
                str(item.get("name")) for item in render_engine.get_burnin_presets()
                if isinstance(item, Mapping) and isinstance(item.get("name"), str) and item.get("name")
            })
            pre_state["actionState"] = {"presetNames": preset_names}
        record = (
            self._handler_results.get(context.get("operationId")) if after else None
        )
        if after:
            pre_state["independentEvidence"] = self._independent_evidence(
                descriptor, targets, value
            )
            if (
                action_id in PRODUCTION_VERIFIED_RESIDUAL_AV_ACTIONS
                and action_id != "cutagent.action.audio.info"
            ):
                if isinstance(record, dict) and action_id.startswith(
                    "cutagent.action.edit."
                ):
                    record["afterSnapshot"] = deepcopy(snapshot)
                pre_state["verifiedSemanticState"] = self._verified_semantic_state(
                    action_id, value, targets, record, pre_state.get("actionState")
                )
        raw = record.get("handlerResult") if isinstance(record, Mapping) else None
        if raw is not None:
            data = raw.get("data", raw) if isinstance(raw, Mapping) else {}
            if action_id == "cutagent.action.clip.offset" and isinstance(data, Mapping):
                data = {
                    "offsets": {
                        "clipName": data.get("clip"),
                        "leftOffsetFrames": data.get("left_offset"),
                        "rightOffsetFrames": data.get("right_offset"),
                    }
                }
            pre_state["semanticData"] = (
                _semantic_data_with_artifact_readback(action_id, data, context, value)
                if isinstance(data, Mapping) else {"value": data}
            )
            if isinstance(data, Mapping) and data.get("actionId") == action_id:
                pre_state["publicResult"] = deepcopy(data)
            proof = data.get("verification") if isinstance(data, Mapping) else None
            if isinstance(proof, Mapping):
                pre_state["evidence"] = {
                    key: item
                    for key, item in proof.items()
                    if key in {"visual", "rendered", "auditioned"}
                    and isinstance(item, Mapping)
                }
        handler_input = deepcopy(dict(value))
        if action_id == "cutagent.action.edit.transition.add":
            timeline = snapshot.get("timeline") if isinstance(snapshot, Mapping) else None
            if not isinstance(timeline, Mapping):
                raise ValidationError(
                    "Prepared transition lacks exact timeline-origin custody."
                )
            public_start = snapshot.get("start")
            public_value = (
                public_start.get("value")
                if isinstance(public_start, Mapping)
                else None
            )
            public_origin = (
                public_value.get("value")
                if isinstance(public_value, Mapping)
                and public_value.get("kind") == "frames"
                else None
            )
            handler_input["timelineStartFrame"] = int(
                timeline.get(
                    "startFrame",
                    public_origin
                    if public_origin is not None
                    else snapshot.get("startFrame", 0),
                )
                or 0
            )
        if action_id == "cutagent.action.edit.from_edl":
            private_input = (
                context.get("privateBindings", {}).get("artifacts", {}).get("input")
            )
            if not isinstance(private_input, Mapping) or not isinstance(
                private_input.get("resolvedPath"), str
            ):
                raise ValidationError(
                    "Prepared EDL import lacks a private managed path."
                )
            handler_input.pop("inputArtifactId", None)
            handler_input["inputPath"] = private_input["resolvedPath"]
        for key in _PATH_FIELDS:
            if isinstance(handler_input.get(key), str):
                output_binding = (
                    context.get("privateBindings", {})
                    .get("artifacts", {})
                    .get("output")
                )
                is_output = key == "outputPath" or (
                    key == "path" and "reserved_output" in descriptor.artifact_roles
                )
                if is_output:
                    if not isinstance(output_binding, Mapping) or not isinstance(
                        output_binding.get("resolvedPath"), str
                    ):
                        raise ValidationError(
                            "Residual output handler lacks carrier-owned private path custody."
                        )
                    handler_input[key] = output_binding["resolvedPath"]
                else:
                    path, _root = self._managed_path(handler_input[key])
                    handler_input[key] = str(path)
        if "reserved_output" in descriptor.artifact_roles \
                and not isinstance(handler_input.get("outputPath"), str):
            output_binding = (
                context.get("privateBindings", {}).get("artifacts", {}).get("output")
            )
            if not isinstance(output_binding, Mapping) or not isinstance(
                output_binding.get("resolvedPath"), str
            ):
                raise ValidationError(
                    "Residual output handler lacks carrier-owned private path custody."
                )
            handler_input["outputPath"] = output_binding["resolvedPath"]
        return {
            "targets": targets,
            "preState": pre_state,
            "artifactBindings": artifacts,
            "protectedState": protected,
            "handlerInput": handler_input,
        }

    def invoke_admitted_handler(self, action_id, context, prepared, handler_input):
        exact_child_action = (
            action_id.startswith("cutagent.action.clip.marker.")
            or action_id == "cutagent.action.clip.offset"
        )
        exact_target = (
            context.get("privateBindings", {}).get("exactTimelineItemTarget")
            if exact_child_action
            else None
        )
        if exact_child_action and not isinstance(exact_target, Mapping):
            raise ValidationError(
                "Residual child execution lacks exact private native target custody."
            )
        exact_target = _mutable_copy(exact_target)
        exact_transition = None
        if action_id == "cutagent.action.edit.transition.add":
            private_bindings = context.get("privateBindings")
            exact_transition = (
                private_bindings.get("exactTransitionTargets")
                if isinstance(private_bindings, Mapping)
                else None
            )
            if not isinstance(exact_transition, Mapping):
                raise ValidationError(
                    "Residual transition execution lacks exact private native target custody."
                )
            exact_transition = _mutable_copy(exact_transition)
        exact_transition_batch = None
        if action_id == "cutagent.action.edit.transition.batch":
            private_bindings = context.get("privateBindings")
            exact_transition_batch = (
                private_bindings.get("exactTransitionBatchTargets")
                if isinstance(private_bindings, Mapping)
                else None
            )
            if not isinstance(exact_transition_batch, (list, tuple)) \
                    or not exact_transition_batch:
                raise ValidationError(
                    "Residual transition batch execution lacks exact private native target custody."
                )
            exact_transition_batch = _mutable_copy(exact_transition_batch)
        env_key = "CUTAGENT_SDK_EXPECTED_CLIP_MOTION_TARGET"
        edl_env_key = "CUTAGENT_SDK_EXPECTED_EDL_TIMELINE_NAME"
        transition_env_key = "CUTAGENT_CLI_SDK_TRANSITION_TARGETS"
        transition_batch_env_key = "CUTAGENT_CLI_SDK_TRANSITION_BATCH_TARGETS"
        track_type_env_key = "CUTAGENT_CLI_SDK_TIMELINE_TRACK_TYPE"
        track_index_env_key = "CUTAGENT_CLI_SDK_TIMELINE_TRACK_INDEX"
        prior_env = os.environ.get(env_key)
        prior_edl_env = os.environ.get(edl_env_key)
        prior_transition_env = os.environ.get(transition_env_key)
        prior_transition_batch_env = os.environ.get(transition_batch_env_key)
        prior_track_type_env = os.environ.get(track_type_env_key)
        prior_track_index_env = os.environ.get(track_index_env_key)
        if exact_target is not None:
            os.environ[env_key] = json.dumps(exact_target, separators=(",", ":"))
        if exact_transition is not None:
            primary = exact_transition["outgoing"] if exact_transition["placement"] == "end" else exact_transition["incoming"]
            os.environ[transition_env_key] = json.dumps(exact_transition, separators=(",", ":"))
            os.environ[track_type_env_key] = str(primary["trackType"])
            os.environ[track_index_env_key] = str(primary["trackIndex"])
        if exact_transition_batch is not None:
            os.environ[transition_batch_env_key] = json.dumps(
                exact_transition_batch, separators=(",", ":")
            )
        if action_id == "cutagent.action.edit.from_edl":
            expected_name = handler_input.get("expectedTimelineName")
            if not isinstance(expected_name, str) or not expected_name:
                raise ValidationError("Prepared EDL import lacks its exact expected name.")
            os.environ[edl_env_key] = expected_name
        try:
            result = super().invoke_admitted_handler(
                action_id, context, prepared, handler_input
            )
        finally:
            if exact_target is not None:
                if prior_env is None:
                    os.environ.pop(env_key, None)
                else:
                    os.environ[env_key] = prior_env
            if exact_transition is not None:
                for key, prior in (
                    (transition_env_key, prior_transition_env),
                    (track_type_env_key, prior_track_type_env),
                    (track_index_env_key, prior_track_index_env),
                ):
                    if prior is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = prior
            if exact_transition_batch is not None:
                if prior_transition_batch_env is None:
                    os.environ.pop(transition_batch_env_key, None)
                else:
                    os.environ[transition_batch_env_key] = prior_transition_batch_env
            if action_id == "cutagent.action.edit.from_edl":
                if prior_edl_env is None:
                    os.environ.pop(edl_env_key, None)
                else:
                    os.environ[edl_env_key] = prior_edl_env
        operation_id = context.get("operationId")
        if isinstance(operation_id, str):
            self._handler_results[operation_id] = {
                "handlerResult": deepcopy(result),
                "handlerInput": deepcopy(handler_input),
                "beforeTimelineItemIds": deepcopy(
                    prepared.get("domain", {})
                    .get("preState", {})
                    .get("semanticState", {})
                    .get("timelineItemIds", [])
                ),
                "beforeActionState": deepcopy(
                    prepared.get("domain", {}).get("preState", {}).get("actionState")
                ),
                "beforeSnapshot": deepcopy(
                    prepared.get("domain", {})
                    .get("preState", {})
                    .get("semanticState", {})
                    .get("snapshot")
                ),
            }
        return result

    def _recover(self, action_id, context, prepared, _failure):
        if action_id in {
            "cutagent.action.edit.transition.add",
            "cutagent.action.edit.transition.batch",
        }:
            operation_id = context.get("operationId")
            record = self._handler_results.get(operation_id) \
                if isinstance(operation_id, str) else None
            prior_rollback = record.get("transitionRollback") \
                if isinstance(record, Mapping) else None
            if isinstance(prior_rollback, Mapping):
                if prior_rollback.get("rollback_performed") is True \
                        and prior_rollback.get("restored_snapshot_verified") is True:
                    return {
                        "outcome": "succeeded", "attempted": True,
                        "manualActionRequired": False,
                    }
                return {
                    "outcome": "manual_required", "attempted": True,
                    "manualActionRequired": True,
                }
            raw = record.get("handlerResult") if isinstance(record, Mapping) else None
            result = raw.get("data", raw) if isinstance(raw, Mapping) else None
            if isinstance(result, Mapping) \
                    and isinstance(result.get("project_db_path"), str) \
                    and bool(result["project_db_path"]) \
                    and isinstance(result.get("backup_path"), str) \
                    and bool(result["backup_path"]):
                try:
                    from ..connection import get_connection
                    from ..core.db_session import restore_project_db_backup_from_mutation_result

                    rollback = restore_project_db_backup_from_mutation_result(
                        get_connection(require_timeline=True),
                        dict(result),
                    )
                except Exception:
                    rollback = {"rollback_performed": False}
                if isinstance(record, dict):
                    record["transitionRollback"] = deepcopy(rollback)
                if rollback.get("rollback_performed") is True:
                    value = prepared.get("lowering", {}).get("normalizedInput") \
                        if isinstance(prepared, Mapping) else None
                    before_snapshot = record.get("beforeSnapshot") \
                        if isinstance(record, Mapping) else None
                    try:
                        restored_snapshot = self._inspect(
                            context, action_id=action_id, value=value, phase="recovery"
                        )
                    except Exception:
                        restored_snapshot = None
                    if not isinstance(before_snapshot, Mapping) \
                            or restored_snapshot != before_snapshot:
                        if isinstance(record, dict):
                            record["transitionRollback"]["restored_snapshot_verified"] = False
                        return {
                            "outcome": "manual_required", "attempted": True,
                            "manualActionRequired": True,
                        }
                    if isinstance(record, dict):
                        record["transitionRollback"]["restored_snapshot_verified"] = True
                    # The prepared-action owner repeats its full target,
                    # protected-state, and artifact comparison before exposing
                    # recovered success.
                    return {
                        "outcome": "succeeded",
                        "attempted": True,
                        "manualActionRequired": False,
                    }
        return {
            "outcome": "manual_required",
            "attempted": True,
            "manualActionRequired": True,
        }
