"""Production prepared actions for Timeline outputs under managed artifact custody.

Native paths exist only in the signed CutAgent CLI process.  The public result
contains opaque artifact identities plus independently recomputed byte, digest,
and media-type evidence that the Bridge publishes through the SDK artifact API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import stat
from types import MappingProxyType
from typing import Any, Mapping

from ..commands import timeline as timeline_commands
from ..connection import get_connection
from ..core import gallery_ops, timeline_inspection_export, timeline_ops
from ..core.resolve_state_lock import exclusive_resolve_state_operation
from ..core.sdk_live_inspection import documented_unique_id
from ..errors import APICallFailed, ValidationError
from .._sdk_low_level_runtime import SDK_TIMELINE_PREPARED_ACTION_SCHEMAS
from .timeline_read_prepared_action import _canonical, _matches_schema


TIMELINE_ARTIFACT_ACTION_CAPABILITIES: Mapping[str, str] = MappingProxyType(
    {
        "cutagent.action.timeline.export": "timeline.import_export",
        "cutagent.action.timeline.inspect_export": "timeline.inspection_export",
        "cutagent.action.timeline.frame_export": "timeline.frame_export",
        "cutagent.action.timeline.grab_still": "timeline.grab_still",
        "cutagent.action.timeline.preview_export": "timeline.preview_export",
        "cutagent.action.timeline.still.grab_all": "timeline.grab_still",
        "cutagent.action.timeline.thumbnail": "timeline.thumbnail",
    }
)
TIMELINE_ARTIFACT_ACTION_IDS = tuple(TIMELINE_ARTIFACT_ACTION_CAPABILITIES)


def _prepared_schema(action_id: str, kind: str) -> Mapping[str, Any]:
    schemas = SDK_TIMELINE_PREPARED_ACTION_SCHEMAS.get(action_id)
    if not isinstance(schemas, Mapping) or not isinstance(schemas.get(kind), Mapping):
        raise ValidationError(f"Timeline artifact {kind} schema is unavailable.")
    return schemas[kind]


def _digest(value: Any) -> str:
    encoded = json.dumps(
        _canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _request_binding(context: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    request = context.get("exactRequestBinding")
    identities = request.get("identities") if isinstance(request, Mapping) else None
    revisions = request.get("revisions") if isinstance(request, Mapping) else None
    if not isinstance(identities, Mapping) or not isinstance(revisions, Mapping):
        raise ValidationError("Timeline artifact request binding is incomplete.")
    target_ids = identities.get("targetIds")
    targets = revisions.get("targets")
    if (
        not isinstance(target_ids, (list, tuple))
        or len(target_ids) < 2
        or len(set(target_ids)) != len(target_ids)
        or not isinstance(targets, Mapping)
        or set(targets) != set(target_ids)
    ):
        raise ValidationError("Timeline artifact target binding is incomplete.")
    return identities, revisions


def _artifact_ids(action_id: str, value: Mapping[str, Any]) -> tuple[str, ...]:
    if action_id in {
        "cutagent.action.timeline.export",
        "cutagent.action.timeline.inspect_export",
        "cutagent.action.timeline.frame_export",
        "cutagent.action.timeline.preview_export",
        "cutagent.action.timeline.thumbnail",
    }:
        values = (
            [str(item["destinationArtifactId"]) for item in value["exports"]]
            if action_id == "cutagent.action.timeline.frame_export" and "exports" in value
            else [str(value["destinationArtifactId"])]
        )
        if action_id == "cutagent.action.timeline.preview_export":
            values.extend(str(item) for item in value["frameArtifactIds"])
    elif action_id == "cutagent.action.timeline.grab_still":
        operation = value["operation"]
        values = (
            [str(operation["destinationArtifactId"])]
            if operation["kind"] == "export"
            else []
        )
    elif action_id == "cutagent.action.timeline.still.grab_all":
        values = [str(item) for item in value["destinationArtifactIds"]]
    else:
        raise ValidationError("Timeline artifact action is not owned.")
    if len(values) != len(set(values)):
        raise ValidationError("Timeline artifact destinations must be unique.")
    return tuple(values)


def _private_records(context: Mapping[str, Any], expected: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    bindings = context.get("privateBindings")
    records = bindings.get("privateManagedArtifacts") if isinstance(bindings, Mapping) else None
    if not isinstance(records, Mapping) or set(records) != set(expected):
        raise ValidationError("Timeline artifact reservation custody is incomplete.")
    normalized: dict[str, dict[str, Any]] = {}
    for artifact_id in expected:
        record = records.get(artifact_id)
        identity = record.get("reservationIdentity") if isinstance(record, Mapping) else None
        if (
            not isinstance(record, Mapping)
            or not isinstance(record.get("path"), str)
            or not os.path.isabs(record["path"])
            or not isinstance(record.get("reservationId"), str)
            or not isinstance(record.get("extension"), str)
            or not isinstance(identity, Mapping)
            or not isinstance(identity.get("device"), int)
            or not isinstance(identity.get("inode"), int)
        ):
            raise ValidationError("Timeline artifact reservation record is malformed.")
        normalized[artifact_id] = dict(record)
    return normalized


def _assert_reserved_inode(record: Mapping[str, Any], *, empty: bool) -> os.stat_result:
    path = Path(str(record["path"]))
    observed = path.lstat()
    identity = record["reservationIdentity"]
    if (
        path.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_dev != identity["device"]
        or observed.st_ino != identity["inode"]
        or stat.S_IMODE(observed.st_mode) & 0o077
        or (empty and observed.st_size != 0)
        or (not empty and observed.st_size < 1)
    ):
        raise ValidationError("Timeline artifact reservation identity changed.")
    return observed


def _native_binding(context: Mapping[str, Any]) -> tuple[str, str]:
    bindings = context.get("privateBindings")
    project_id = bindings.get("nativeProjectId") if isinstance(bindings, Mapping) else None
    timeline_id = bindings.get("nativeTimelineId") if isinstance(bindings, Mapping) else None
    if not isinstance(project_id, str) or not project_id or not isinstance(timeline_id, str) or not timeline_id:
        raise ValidationError("Timeline artifact native identity custody is incomplete.")
    return project_id, timeline_id


def _connection(context: Mapping[str, Any]) -> Any:
    expected_project, expected_timeline = _native_binding(context)
    conn = get_connection(require_project=True, require_timeline=True)
    if documented_unique_id(conn.project) != expected_project:
        raise ValidationError("Active project changed after artifact authorization.")
    if documented_unique_id(conn.timeline) != expected_timeline:
        raise ValidationError("Active Timeline changed after artifact authorization.")
    return conn


def _protected_snapshot(conn: Any) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for track_type in ("video", "audio", "subtitle"):
        count = int(conn.timeline.GetTrackCount(track_type) or 0)
        for index in range(1, count + 1):
            items = conn.timeline.GetItemListInTrack(track_type, index) or []
            for item in items:
                native_id = documented_unique_id(item)
                if not native_id:
                    raise ValidationError("Timeline protected-state item lacks a native identity.")
                rows.append(
                    {
                        "trackType": track_type,
                        "trackIndex": index,
                        "nativeId": native_id,
                        "start": int(item.GetStart()),
                        "end": int(item.GetEnd()),
                    }
                )
    playhead = timeline_ops.get_playhead(conn)
    return {
        "projectNativeId": documented_unique_id(conn.project),
        "timelineNativeId": documented_unique_id(conn.timeline),
        "timelineDigest": _digest(rows),
        "playhead": {
            "frame": int(playhead["frame"]),
            "timecode": str(playhead["timecode"]),
        },
    }


def _protected_difference_summary(before: Mapping[str, Any], after: Mapping[str, Any]) -> str:
    differences = []
    for key in ("projectNativeId", "timelineNativeId", "timelineDigest", "playhead"):
        if before.get(key) == after.get(key):
            continue
        if key == "playhead":
            for field_name in ("frame", "timecode"):
                old = (before.get(key) or {}).get(field_name)
                new = (after.get(key) or {}).get(field_name)
                if old != new:
                    differences.append({"field": f"playhead.{field_name}", "before": old, "after": new})
        else:
            differences.append({"field": key, "beforeDigest": _digest(before.get(key)), "afterDigest": _digest(after.get(key))})
    return "Protected DaVinci Resolve state differs: " + json.dumps(differences, sort_keys=True)


def _gallery_count(conn: Any) -> int:
    return len(gallery_ops.list_stills(conn))


def _media_type(path: Path) -> str:
    guessed = mimetypes.guess_type(path.name)[0]
    if guessed:
        return guessed
    return {
        ".drt": "application/x-davinci-resolve-timeline",
        ".edl": "application/x-edl",
        ".fcpxml": "application/xml",
        ".otio": "application/vnd.opentimelineio+json",
    }.get(path.suffix.lower(), "application/octet-stream")


def _file_receipt(artifact_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
    observed = _assert_reserved_inode(record, empty=False)
    path = Path(str(record["path"]))
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.lstat()
    if (
        after.st_dev != observed.st_dev
        or after.st_ino != observed.st_ino
        or after.st_size != observed.st_size
        or after.st_mtime_ns != observed.st_mtime_ns
    ):
        raise ValidationError("Timeline artifact changed during digest readback.")
    return {
        "artifactId": artifact_id,
        "mediaType": _media_type(path),
        "byteCount": observed.st_size,
        "sha256": digest.hexdigest(),
    }


def _stage_directory(record: Mapping[str, Any], label: str) -> Path:
    destination = Path(str(record["path"]))
    token = hashlib.sha256(f"{destination.name}:{label}".encode()).hexdigest()[:24]
    staging = destination.parent / f".{destination.name}.{token}.staging"
    if staging.exists() or staging.is_symlink():
        raise ValidationError("Timeline artifact staging custody is not clean.")
    staging.mkdir(mode=0o700)
    return staging


def _copy_into_reservation(source: Path, record: Mapping[str, Any]) -> None:
    source_stat = source.lstat()
    if source.is_symlink() or not stat.S_ISREG(source_stat.st_mode) or source_stat.st_size < 1:
        raise APICallFailed("Timeline artifact native output is missing or empty.")
    _assert_reserved_inode(record, empty=True)
    destination = Path(str(record["path"]))
    flags = os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(destination, flags)
    try:
        opened = os.fstat(descriptor)
        identity = record["reservationIdentity"]
        if opened.st_dev != identity["device"] or opened.st_ino != identity["inode"]:
            raise ValidationError("Timeline artifact reservation changed before publication.")
        with source.open("rb") as input_handle, os.fdopen(os.dup(descriptor), "wb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
            output_handle.flush()
            os.fsync(output_handle.fileno())
    finally:
        os.close(descriptor)
    _assert_reserved_inode(record, empty=False)


def _record_ref(position: Mapping[str, Any], conn: Any) -> str:
    value = position["value"]
    if value["kind"] != "frames":
        return str(value["value"])
    # Public SDK record-frame positions are absolute timeline coordinates, while
    # the CutAgent CLI frame-reference parser accepts frame values as offsets
    # from the active timeline start. Lower exactly once at this boundary.
    start_frame = int(conn.timeline.GetStartFrame())
    return f"{int(value['value']) - start_frame}f"


def _export_gallery_stills(conn: Any, stills: list[Any], staging: Path, fmt: str) -> list[Path]:
    gallery = conn.project.GetGallery()
    album = gallery.GetCurrentStillAlbum() if gallery else None
    exporter = getattr(album, "ExportStills", None)
    if not callable(exporter):
        raise APICallFailed("Current gallery album cannot export grabbed stills.")
    attempts = gallery_ops._export_stills_native_variants(exporter, stills, str(staging), "sdk", fmt.upper())
    if not any(attempt.get("success") for attempt in attempts):
        raise APICallFailed("DaVinci Resolve did not export the grabbed still set.")
    extension = ".jpg" if fmt in {"jpg", "jpeg"} else f".{fmt}"
    outputs = sorted(path for path in staging.iterdir() if path.is_file() and path.suffix.lower() == extension)
    if len(outputs) != len(stills):
        raise APICallFailed("Grabbed still export count did not match the exact destination set.")
    return outputs


@dataclass(frozen=True)
class TimelineArtifactPreparedActionDescriptor:
    action_id: str
    capability_id: str
    _private_timeline_inspector: Any = field(default=None, init=False, repr=False, compare=False)

    operation_class = "mutation"
    version = 1

    @property
    def command_id(self) -> str:
        return self.action_id.removeprefix("cutagent.action.")

    def bind_private_timeline_inspector(self, callback: Any) -> None:
        if not callable(callback):
            raise TypeError("Timeline artifact private inspector must be callable.")
        object.__setattr__(self, "_private_timeline_inspector", callback)

    def invoke_admitted_handler(self, *_args: Any, **_kwargs: Any) -> None:
        """Expose this fixed owner to host binding without opening a second dispatch path."""
        raise ValidationError(
            "Timeline artifact actions execute only through their fixed prepared descriptor."
        )

    def _assert_fresh_binding(self, context: Mapping[str, Any]) -> None:
        if not callable(self._private_timeline_inspector):
            raise ValidationError("Timeline artifact action lacks fresh private inspection.")
        identities, revisions = _request_binding(context)
        inspected = self._private_timeline_inspector(
            {"projectId": identities["projectId"], "timelineId": identities["timelineId"]}
        )
        snapshot = inspected.get("snapshot") if isinstance(inspected, Mapping) else None
        project = inspected.get("projectBinding") if isinstance(inspected, Mapping) else None
        runtime_timeline = context.get("timeline")
        expected_guard = (
            runtime_timeline.get("mutationGuard")
            if isinstance(runtime_timeline, Mapping)
            else None
        )
        timeline_id = snapshot.get("id") if isinstance(snapshot, Mapping) else None
        if timeline_id is None and isinstance(snapshot, Mapping):
            timeline_id = snapshot.get("timeline", {}).get("id") if isinstance(snapshot.get("timeline"), Mapping) else None
        if (
            not isinstance(snapshot, Mapping)
            or not isinstance(project, Mapping)
            or not isinstance(expected_guard, str)
            or inspected.get("mutationGuard") != expected_guard
            or timeline_id != identities.get("timelineId")
            or snapshot.get("revision") != revisions.get("timeline")
            or project.get("projectLibraryId") != identities.get("projectLibraryId")
            or project.get("projectLibraryRevision") != revisions.get("projectLibrary")
            or project.get("projectId") != identities.get("projectId")
            or project.get("projectRevision") != revisions.get("project")
        ):
            raise ValidationError("Timeline artifact authoritative project or Timeline revision is stale.")

    def validate_input(self, value: Any) -> dict[str, Any]:
        schema = _prepared_schema(self.action_id, "input")
        if not isinstance(schema, Mapping) or not _matches_schema(schema, value):
            raise ValidationError("Timeline artifact input does not match its exact public schema.")
        canonical = _canonical(value)
        ids = _artifact_ids(self.action_id, canonical)
        if self.action_id == "cutagent.action.timeline.preview_export":
            record_range = canonical["range"]
            frames = list(range(record_range["start"], record_range["endExclusive"], canonical["step"]))
            if not frames or len(frames) != len(canonical["frameArtifactIds"]):
                raise ValidationError("Preview frame destinations do not match its exact sampled range.")
        if self.action_id == "cutagent.action.timeline.still.grab_all" and not ids:
            raise ValidationError("Bulk still capture requires explicit artifact destinations.")
        return canonical

    def _state(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        identities, revisions = _request_binding(context)
        runtime_project = context.get("project")
        runtime_timeline = context.get("timeline")
        if (
            not isinstance(runtime_project, Mapping)
            or not isinstance(runtime_timeline, Mapping)
            or value.get("projectId") != identities.get("projectId")
            or value.get("timelineId") != identities.get("timelineId")
            or value.get("revision") != revisions.get("timeline")
            or runtime_project.get("projectId") != identities.get("projectId")
            or runtime_timeline.get("timelineId") != identities.get("timelineId")
        ):
            raise ValidationError("Timeline artifact public identity or revision is stale.")
        self._assert_fresh_binding(context)
        artifact_ids = _artifact_ids(self.action_id, value)
        records = _private_records(context, artifact_ids)
        for record in records.values():
            _assert_reserved_inode(record, empty=True)
        expected_targets = [identities["projectId"], identities["timelineId"], *artifact_ids]
        if list(identities["targetIds"]) != expected_targets:
            raise ValidationError("Timeline artifact target order or identity is incomplete.")
        conn = _connection(context)
        protected = _protected_snapshot(conn)
        return {
            "targets": [
                {
                    "kind": "project" if target_id == identities["projectId"] else "timeline" if target_id == identities["timelineId"] else "artifact",
                    "stableId": target_id,
                    "revision": revisions["targets"][target_id],
                    "projectId": identities["projectId"],
                    "timelineId": identities["timelineId"],
                }
                for target_id in expected_targets
            ],
            "preState": {
                "protected": protected,
                "artifactIds": list(artifact_ids),
                **(
                    {"galleryCount": _gallery_count(conn)}
                    if self.action_id in {"cutagent.action.timeline.grab_still", "cutagent.action.timeline.still.grab_all"}
                    else {}
                ),
            },
        }

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        state = self._state(context, value)
        mutation_base = context.get("mutationBase")
        if not isinstance(mutation_base, Mapping):
            raise ValidationError("Timeline artifact action lacks its carrier mutation binding.")
        has_artifact_custody = bool(state["preState"]["artifactIds"])
        effect_targets = []
        for target in state["targets"]:
            private_kind = target["kind"]
            if private_kind == "artifact":
                public_kind = "media"
            elif private_kind in {"project", "timeline"}:
                public_kind = private_kind
            else:
                raise ValidationError("Timeline artifact impact target has an unsupported kind.")
            effect_targets.append({
                "kind": public_kind,
                "stableId": target["stableId"],
                "revision": target["revision"],
            })
        return {
            **state,
            "impact": {
                **dict(mutation_base),
                "status": "mutation",
                "effects": [{
                    "operation": self.command_id,
                    "kind": "create",
                    "trackTypes": [],
                    "targets": effect_targets,
                    "placementIntent": "explicit",
                    "broad": False,
                    "ambiguous": False,
                    "complete": True,
                }],
                "closedComposition": True,
                "complete": True,
                "ambiguous": False,
                "broad": False,
                "executableStableTargetPrecondition": True,
                "verificationPolicy": {
                    "minimumEvidence": [
                        "readback", "structural", *(["file"] if has_artifact_custody else []),
                    ],
                    "requireProtectedStatePreserved": True,
                    "protectedTargetEvidence": "every_declared_target",
                },
            },
            "lowering": {"input": dict(value)},
            "verification": {
                "minimumEvidence": [
                    *(["artifact_readback"] if has_artifact_custody else []),
                    "context_readback", "protected_state_readback",
                ],
                "protectedState": ["project_identity", "timeline_identity", "timeline_structure", "playhead", "artifact_destination"],
            },
            "recovery": {
                "strategy": "restore_playhead_and_clear_reserved_outputs",
                "galleryMutationMayRequireManualRecovery": self.action_id in {"cutagent.action.timeline.grab_still", "cutagent.action.timeline.still.grab_all"},
            },
        }

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        return self._state(context, prepared["lowering"]["input"])

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        value = prepared["lowering"]["input"]
        self._assert_fresh_binding(context)
        artifact_ids = _artifact_ids(self.action_id, value)
        records = _private_records(context, artifact_ids)
        conn = _connection(context)
        result: dict[str, Any] = {"artifacts": []}
        staging: Path | None = None
        try:
            if self.action_id == "cutagent.action.timeline.grab_still" and value["operation"]["kind"] == "gallery":
                before = _gallery_count(conn)
                timeline_ops.grab_still(conn)
                result.update(galleryBefore=before, galleryAfter=_gallery_count(conn))
                return result
            anchor = records[artifact_ids[0]]
            staging = _stage_directory(anchor, self.action_id)
            if self.action_id == "cutagent.action.timeline.export":
                target = staging / f"timeline.{anchor['extension']}"
                timeline_ops.export_timeline(conn, str(target), str(value["format"]))
                _copy_into_reservation(target, anchor)
            elif self.action_id == "cutagent.action.timeline.inspect_export":
                target = staging / "timeline-inspection.json"
                document = timeline_inspection_export.build_timeline_inspection(conn)
                target.write_text(
                    json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                result["inspectionComplete"] = bool(document["coverage"]["complete"])
                result["unreadableFieldCount"] = int(document["coverage"]["unreadableFieldCount"])
                _copy_into_reservation(target, anchor)
            elif self.action_id == "cutagent.action.timeline.frame_export":
                exports = value.get("exports")
                if isinstance(exports, list):
                    targets = [
                        (
                            _record_ref(item["position"], conn),
                            staging / f"frame-{index:04d}.{records[str(item['destinationArtifactId'])]['extension']}",
                        )
                        for index, item in enumerate(exports)
                    ]
                    native = timeline_commands._export_frame_targets(conn, targets=targets)
                    if not native.get("restored_playhead") or len(native.get("frames") or []) != len(exports):
                        raise APICallFailed("Frame exports did not restore the original playhead or exact output set.")
                    for item, (_frame_ref, source) in zip(exports, targets):
                        _copy_into_reservation(source, records[str(item["destinationArtifactId"])])
                    result["positions"] = [item["position"] for item in exports]
                else:
                    target = staging / f"frame.{anchor['extension']}"
                    with exclusive_resolve_state_operation(operation="sdk.timeline.frame_export"):
                        native = timeline_commands._export_single_timeline_frame(
                            conn,
                            frame_ref=_record_ref(value["position"], conn),
                            resolved_path=target,
                            requested_output_path=str(target),
                        )
                    if not native.get("restored_playhead"):
                        raise APICallFailed("Frame export did not restore the original playhead.")
                    _copy_into_reservation(target, anchor)
                expected_playhead = prepared["preState"]["protected"]["playhead"]
                settled_frame = (
                    timeline_ops.get_playhead(conn).get("frame")
                    if isinstance(exports, list)
                    else timeline_ops.set_playhead(
                        conn,
                        expected_playhead["timecode"],
                        return_details=True,
                        frame_tolerance=0,
                    ).get("final_frame")
                )
                if int(settled_frame) != int(expected_playhead["frame"]):
                    raise APICallFailed("Frame export playhead restoration did not remain exact through artifact publication.")
                result["originalPlayheadRestored"] = True
            elif self.action_id == "cutagent.action.timeline.grab_still":
                target = staging / f"still.{anchor['extension']}"
                timeline_ops.grab_still(conn, output_path=str(target))
                _copy_into_reservation(target, anchor)
            elif self.action_id == "cutagent.action.timeline.thumbnail":
                target = staging / f"thumbnail.{anchor['extension']}"
                timeline_commands._export_current_frame_as_still(
                    conn,
                    resolved_path=target,
                    requested_output_path=str(target),
                    error_message="Failed to export the managed Timeline thumbnail.",
                )
                _copy_into_reservation(target, anchor)
            elif self.action_id == "cutagent.action.timeline.preview_export":
                frame_ids = tuple(value["frameArtifactIds"])
                frame_refs = [f"{frame}f" for frame in range(value["range"]["start"], value["range"]["endExclusive"], value["step"])]
                frame_dir = staging / "frames"
                sequence = timeline_commands._export_frame_sequence(
                    conn, frame_refs=frame_refs, out_dir=frame_dir, prefix="preview", extension="png"
                )
                if not sequence.get("restored_playhead") or len(sequence["frames"]) != len(frame_ids):
                    raise APICallFailed("Preview export did not restore the playhead or exact frame set.")
                paths = [Path(str(item["output_path"])) for item in sequence["frames"]]
                preview = staging / f"preview.{anchor['extension']}"
                timeline_commands._write_preview_video(paths, preview, fps=float(value["frameRate"]))
                _copy_into_reservation(preview, anchor)
                for artifact_id, source in zip(frame_ids, paths):
                    _copy_into_reservation(source, records[artifact_id])
                result["originalPlayheadRestored"] = True
            elif self.action_id == "cutagent.action.timeline.still.grab_all":
                before = _gallery_count(conn)
                native = timeline_ops.grab_all_stills(conn, str(value["source"]))
                stills = native.get("stills")
                if not isinstance(stills, list) or len(stills) != len(artifact_ids):
                    raise APICallFailed("Grabbed still count did not match the reserved destination set.")
                outputs = _export_gallery_stills(conn, stills, staging, str(value["format"]))
                for artifact_id, source in zip(artifact_ids, outputs):
                    _copy_into_reservation(source, records[artifact_id])
                result.update(galleryBefore=before, galleryAfter=_gallery_count(conn))
            else:
                raise ValidationError("Timeline artifact action has no production executor.")
            result["artifacts"] = [_file_receipt(artifact_id, records[artifact_id]) for artifact_id in artifact_ids]
            return result
        finally:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        value = prepared["lowering"]["input"]
        artifact_ids = _artifact_ids(self.action_id, value)
        records = _private_records(context, artifact_ids)
        actual = [_file_receipt(artifact_id, records[artifact_id]) for artifact_id in artifact_ids]
        conn = _connection(context)
        protected = _protected_snapshot(conn)
        protected_match = protected == prepared["preState"]["protected"]
        artifact_match = actual == result.get("artifacts")
        gallery_match = True
        gallery_only = (
            self.action_id == "cutagent.action.timeline.grab_still"
            and value["operation"]["kind"] == "gallery"
        )
        if gallery_only:
            expected_gallery = prepared["preState"]["galleryCount"] + 1
            gallery_match = result.get("galleryAfter") == expected_gallery == _gallery_count(conn)
        elif self.action_id == "cutagent.action.timeline.still.grab_all":
            expected_gallery = prepared["preState"]["galleryCount"] + len(artifact_ids)
            gallery_match = result.get("galleryAfter") == expected_gallery == _gallery_count(conn)
        passed = protected_match and artifact_match and gallery_match
        evidence_value = {"protected": protected, "artifacts": actual, "galleryMatched": gallery_match}
        evidence = [
            {
                "modality": "readback", "digest": _digest(evidence_value),
                "summary": (
                    "Exact project, Timeline, playhead, and gallery count matched independent readback."
                    if protected_match and gallery_only and gallery_match
                    else "Exact project, Timeline, playhead, and artifact targets matched independent readback."
                    if protected_match and artifact_match and gallery_match
                    else "Timeline artifact context or output comparison failed."
                ),
            },
            {"modality": "structural", "digest": _digest(protected), "summary": ("Protected Timeline structure remained unchanged." if protected_match
                else _protected_difference_summary(prepared["preState"]["protected"], protected))},
        ]
        if artifact_ids:
            evidence.insert(0, {
                "modality": "file", "digest": _digest(actual),
                "summary": ("Managed artifact bytes, media types, sizes, and digests matched readback."
                            if artifact_match else "Managed artifact readback differs from the execution receipt."),
            })
        return {
            "outcome": "passed" if passed else "failed",
            "evidence": evidence,
            "protectedStatePreserved": protected_match,
        }

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        value = prepared["lowering"]["input"]
        artifact_ids = _artifact_ids(self.action_id, value)
        attempted = True
        restored = False
        try:
            records = _private_records(context, artifact_ids)
            for record in records.values():
                observed = Path(str(record["path"])).lstat()
                _assert_reserved_inode(record, empty=observed.st_size == 0)
                flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(str(record["path"]), flags)
                with os.fdopen(descriptor, "r+b", buffering=0) as handle:
                    handle.truncate(0)
                    os.fsync(handle.fileno())
                _assert_reserved_inode(record, empty=True)
            conn = _connection(context)
            timeline_ops.set_playhead(conn, prepared["preState"]["protected"]["playhead"]["timecode"], return_details=True, frame_tolerance=0)
            restored = _protected_snapshot(conn) == prepared["preState"]["protected"]
        except Exception:
            restored = False
        gallery_risk = self.action_id == "cutagent.action.timeline.still.grab_all" or (
            self.action_id == "cutagent.action.timeline.grab_still" and value["operation"]["kind"] == "gallery"
        )
        return {
            "outcome": "succeeded" if restored and not gallery_risk else "manual_required",
            "attempted": attempted,
            "manualActionRequired": not restored or gallery_risk,
        }

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        del context
        value = prepared["lowering"]["input"]
        artifacts = list(result.get("artifacts") or [])
        if self.action_id == "cutagent.action.timeline.grab_still":
            still = (
                {"kind": "gallery", "grabbed": True}
                if value["operation"]["kind"] == "gallery"
                else {"kind": "export", "artifact": artifacts[0]}
            )
            projected = {
                "actionId": self.action_id,
                "still": still,
                "revisionChange": {"before": value["revision"], "after": value["revision"], "changed": False},
            }
        elif self.action_id == "cutagent.action.timeline.frame_export":
            projected = (
                {
                    "actionId": self.action_id,
                    "exports": [
                        {"artifact": artifact, "position": item["position"]}
                        for artifact, item in zip(artifacts, value["exports"])
                    ],
                    "originalPlayheadRestored": True,
                }
                if "exports" in value
                else {"actionId": self.action_id, "artifact": artifacts[0], "position": value["position"], "originalPlayheadRestored": True}
            )
        elif self.action_id == "cutagent.action.timeline.preview_export":
            projected = {"actionId": self.action_id, "artifact": artifacts[0], "frameArtifacts": artifacts[1:], "originalPlayheadRestored": True}
        elif self.action_id == "cutagent.action.timeline.still.grab_all":
            projected = {"actionId": self.action_id, "artifacts": artifacts}
        else:
            projected = {"actionId": self.action_id, "artifact": artifacts[0]}
        canonical = _canonical(projected)
        self._assert_path_free(canonical)
        return canonical

    @staticmethod
    def _assert_path_free(value: Any) -> None:
        if isinstance(value, Mapping):
            forbidden = {"path", "outputPath", "framesDirectory", "lowering", "engine", "commandId"}
            if forbidden.intersection(value):
                raise ValidationError("Timeline artifact public result contains private execution data.")
            for item in value.values():
                TimelineArtifactPreparedActionDescriptor._assert_path_free(item)
        elif isinstance(value, list):
            for item in value:
                TimelineArtifactPreparedActionDescriptor._assert_path_free(item)
        elif isinstance(value, str) and (
            value.startswith(("/Users/", "/home/", "/tmp/", "\\\\"))
            or (len(value) >= 3 and value[0].isalpha() and value[1:3] in {":\\", ":/"})
        ):
            raise ValidationError("Timeline artifact public result contains a local path.")

    def validate_public_result(self, value: Any) -> bool:
        schema = _prepared_schema(self.action_id, "result")
        try:
            self._assert_path_free(value)
            return isinstance(schema, Mapping) and _matches_schema(schema, value)
        except (TypeError, ValueError, ValidationError):
            return False


def timeline_artifact_prepared_action_production_contribution() -> Mapping[str, TimelineArtifactPreparedActionDescriptor]:
    return MappingProxyType(
        {
            action_id: TimelineArtifactPreparedActionDescriptor(action_id, capability_id)
            for action_id, capability_id in TIMELINE_ARTIFACT_ACTION_CAPABILITIES.items()
        }
    )


__all__ = [
    "TIMELINE_ARTIFACT_ACTION_IDS",
    "TIMELINE_ARTIFACT_ACTION_CAPABILITIES",
    "TimelineArtifactPreparedActionDescriptor",
    "timeline_artifact_prepared_action_production_contribution",
]
