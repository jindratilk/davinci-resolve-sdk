"""Prepared export of one project-settings preset into managed SDK custody."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Callable, Mapping

from ..connection import get_connection
from ..core.project_preset_api import export_project_preset, project_preset_records
from ..core.sdk_live_inspection import documented_unique_id
from ..errors import APICallFailed, ValidationError
from .project_render_storage_media_prepared_action import (
    _assert_native_project_binding,
    _canonical,
    _evidence,
    _project_protected_state,
    _target,
)


ACTION_ID = "cutagent.action.project.preset.export"
CAPABILITY_ID = "project.preset_import_export"
_ARTIFACT_ID = re.compile(r"^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$")
_MAX_BYTES = 16 * 1024 * 1024


def _reservation(context: Mapping[str, Any], artifact_id: str) -> dict[str, Any]:
    mutation_base = context.get("mutationBase")
    operation_id = mutation_base.get("operationId") if isinstance(mutation_base, Mapping) else None
    bindings = context.get("privateBindings")
    records = bindings.get("privateManagedArtifacts") if isinstance(bindings, Mapping) else None
    if not isinstance(records, Mapping) or set(records) != {artifact_id}:
        raise ValidationError("Project preset export requires one exact managed artifact reservation.")
    record = records.get(artifact_id)
    identity = record.get("reservationIdentity") if isinstance(record, Mapping) else None
    if (
        not isinstance(record, Mapping)
        or not isinstance(record.get("path"), str)
        or not os.path.isabs(record["path"])
        or not isinstance(record.get("reservationId"), str)
        or not isinstance(operation_id, str)
        or not operation_id
        or record.get("reservationId") != operation_id
        or not isinstance(identity, Mapping)
        or not isinstance(identity.get("device"), int)
        or isinstance(identity.get("device"), bool)
        or not isinstance(identity.get("inode"), int)
        or isinstance(identity.get("inode"), bool)
    ):
        raise ValidationError("Project preset export reservation custody is incomplete.")
    return dict(record)


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
        or (not empty and not 0 < observed.st_size <= _MAX_BYTES)
    ):
        raise ValidationError("Project preset export reservation identity changed.")
    return observed


def _snapshot(context: Mapping[str, Any]) -> dict[str, Any]:
    conn = get_connection(require_project=True)
    _assert_native_project_binding(context, conn)
    raw_settings = conn.project.GetSetting()
    if not isinstance(raw_settings, Mapping):
        raise APICallFailed("DaVinci Resolve project settings readback is unavailable.")
    timeline = getattr(conn, "timeline", None)
    timeline_id = documented_unique_id(timeline) if timeline is not None else None
    if timeline is not None and (not isinstance(timeline_id, str) or not timeline_id):
        raise APICallFailed("DaVinci Resolve current Timeline identity readback is unavailable.")
    page_getter = getattr(getattr(conn, "resolve", None), "GetCurrentPage", None)
    page = page_getter() if callable(page_getter) else None
    if not isinstance(page, str) or not page:
        raise APICallFailed("DaVinci Resolve current page readback is unavailable.")
    return {
        "presets": _canonical(project_preset_records(conn.project)),
        "settings": _canonical(raw_settings),
        "timelineNativeId": timeline_id,
        "currentPage": page,
        "protected": _project_protected_state(conn, context),
    }


def _read_receipt(artifact_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
    before = _assert_reserved_inode(record, empty=False)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(record["path"]), flags)
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        if not os.path.samestat(before, opened):
            raise ValidationError("Project preset export reservation changed before readback.")
        content = source.read(_MAX_BYTES + 1)
        closed = os.fstat(source.fileno())
    after = Path(str(record["path"])).lstat()
    if (
        len(content) != before.st_size
        or not os.path.samestat(opened, closed)
        or not os.path.samestat(opened, after)
        or (opened.st_size, opened.st_mtime_ns) != (closed.st_size, closed.st_mtime_ns)
        or (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
    ):
        raise ValidationError("Project preset export changed during readback.")
    return {
        "artifactId": artifact_id,
        "mediaType": "application/octet-stream",
        "byteCount": len(content),
        "sha256": f"sha256:{hashlib.sha256(content).hexdigest()}",
    }


def _copy_into_reservation(source: Path, record: Mapping[str, Any]) -> None:
    source_stat = source.lstat()
    if source.is_symlink() or not stat.S_ISREG(source_stat.st_mode) or not 0 < source_stat.st_size <= _MAX_BYTES:
        raise APICallFailed("DaVinci Resolve project preset export is missing or invalid.")
    _assert_reserved_inode(record, empty=True)
    flags = os.O_WRONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(record["path"]), flags)
    opened = os.fstat(descriptor)
    identity = record["reservationIdentity"]
    if opened.st_dev != identity["device"] or opened.st_ino != identity["inode"]:
        os.close(descriptor)
        raise ValidationError("Project preset export reservation changed before publication.")
    try:
        source_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        source_descriptor = os.open(source, source_flags)
        try:
            opened_source = os.fstat(source_descriptor)
            if not os.path.samestat(source_stat, opened_source):
                raise ValidationError("Project preset staging identity changed before publication.")
            remaining = source_stat.st_size
            while remaining:
                chunk = os.read(source_descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    raise APICallFailed("Project preset staging became shorter during publication.")
                remaining -= len(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(descriptor, view)
                    if written < 1:
                        raise OSError("managed artifact write made no progress")
                    view = view[written:]
            if os.read(source_descriptor, 1):
                raise APICallFailed("Project preset staging grew during publication.")
            closed_source = os.fstat(source_descriptor)
            if (
                not os.path.samestat(opened_source, closed_source)
                or (opened_source.st_size, opened_source.st_mtime_ns)
                != (closed_source.st_size, closed_source.st_mtime_ns)
            ):
                raise APICallFailed("Project preset staging changed during publication.")
        finally:
            os.close(source_descriptor)
        os.fsync(descriptor)
    except Exception:
        try:
            current = os.fstat(descriptor)
            if current.st_dev == identity["device"] and current.st_ino == identity["inode"]:
                os.ftruncate(descriptor, 0)
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        raise
    os.close(descriptor)
    _assert_reserved_inode(record, empty=False)


@dataclass(frozen=True)
class ProjectPresetExportDescriptor:
    managed_artifact_path: Callable[..., str]
    signed_artifact_targets: Callable[..., list[dict[str, Any]]]
    specific_impact: Callable[..., dict[str, Any]]
    project_result_builder: Callable[..., dict[str, Any]]
    public_result_validator: Callable[[str, Any], bool]

    action_id = ACTION_ID
    capability_id = CAPABILITY_ID
    operation_class = "mutation"
    version = 1

    @property
    def command_id(self) -> str:
        return "project.preset.export"

    def validate_input(self, value: Any) -> dict[str, str]:
        if not isinstance(value, Mapping) or set(value) != {"name", "destinationArtifactId"}:
            raise ValidationError("Project preset export input must contain an exact name and destinationArtifactId.")
        name = value.get("name")
        artifact_id = value.get("destinationArtifactId")
        if not isinstance(name, str) or not name or len(name) > 1024 or "\x00" in name:
            raise ValidationError("Project preset export name must be a bounded nonempty string.")
        if (
            not isinstance(artifact_id, str)
            or len(artifact_id) > 256
            or _ARTIFACT_ID.fullmatch(artifact_id) is None
        ):
            raise ValidationError("Project preset export artifact identity is invalid.")
        return {"name": name, "destinationArtifactId": artifact_id}

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        before = _snapshot(context)
        if sum(row["name"] == value["name"] for row in before["presets"]) != 1:
            raise ValidationError("Project preset export requires one exact existing preset.")
        artifact_id = value["destinationArtifactId"]
        path = self.managed_artifact_path(context, artifact_id, existing=False, directory=False)
        record = _reservation(context, artifact_id)
        if str(Path(path)) != str(Path(record["path"])):
            raise ValidationError("Project preset export reservation path drifted.")
        _assert_reserved_inode(record, empty=True)
        project_target = _target(context)
        targets = self.signed_artifact_targets(context, project_target, artifact_id)
        return {
            "targets": targets,
            "preState": before,
            "impact": self.specific_impact(context, self.action_id, value, targets),
            "lowering": {"input": dict(value), "privateReservation": record},
            "verification": {"minimumEvidence": ["artifact_readback", "structural_readback", "context_readback"]},
            "recovery": {"strategy": "inspect_artifact_destination"},
        }

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        _assert_reserved_inode(prepared["lowering"]["privateReservation"], empty=True)
        return {"targets": prepared["targets"], "preState": _snapshot(context)}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        if _snapshot(context) != prepared["preState"]:
            raise ValidationError("Project state changed after preset export preparation.")
        value = prepared["lowering"]["input"]
        record = prepared["lowering"]["privateReservation"]
        _assert_reserved_inode(record, empty=True)
        reservation = Path(str(record["path"]))
        with tempfile.TemporaryDirectory(prefix=".cutagent-sdk-project-preset-export-", dir=reservation.parent) as folder:
            staging = Path(folder) / "preset"
            conn = get_connection(require_project=True)
            _assert_native_project_binding(context, conn)
            native_result = export_project_preset(conn.project, value["name"], str(staging))
            if native_result.get("exported") is not True:
                raise APICallFailed("DaVinci Resolve did not confirm project preset export.")
            _copy_into_reservation(staging, record)
        receipt = _read_receipt(value["destinationArtifactId"], record)
        if (
            native_result.get("sizeBytes") != receipt["byteCount"]
            or f"sha256:{native_result.get('sha256')}" != receipt["sha256"]
        ):
            raise APICallFailed("Managed project preset bytes differ from native export readback.")
        return {"artifact": receipt}

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        before = prepared["preState"]
        after = _snapshot(context)
        artifact_id = prepared["lowering"]["input"]["destinationArtifactId"]
        actual = _read_receipt(artifact_id, prepared["lowering"]["privateReservation"])
        expected = result.get("artifact") if isinstance(result, Mapping) else None
        state_preserved = after == before
        passed = state_preserved and actual == expected
        return {
            "outcome": "passed" if passed else "failed",
            "evidence": _evidence(self.action_id, {"artifact": actual, "statePreserved": state_preserved}),
            "protectedStatePreserved": state_preserved,
        }

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        attempted = False
        try:
            if _snapshot(context) != prepared["preState"]:
                return {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}
            record = prepared["lowering"]["privateReservation"]
            path = Path(str(record["path"]))
            observed = path.lstat()
            _assert_reserved_inode(record, empty=observed.st_size == 0)
            if observed.st_size:
                attempted = True
                flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(str(record["path"]), flags)
                with os.fdopen(descriptor, "r+b", buffering=0) as handle:
                    opened = os.fstat(handle.fileno())
                    if not os.path.samestat(observed, opened):
                        raise ValidationError("Project preset export reservation changed before recovery.")
                    handle.truncate(0)
                    os.fsync(handle.fileno())
            _assert_reserved_inode(record, empty=True)
            return {"outcome": "succeeded", "attempted": attempted, "manualActionRequired": False}
        except Exception:
            return {"outcome": "manual_required", "attempted": attempted, "manualActionRequired": True}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        del context
        return self.project_result_builder(
            self.action_id,
            target={"name": prepared["lowering"]["input"]["name"]},
            data={"artifact": result["artifact"]},
            evidence=("artifact_readback", "structural_readback", "context_readback"),
            retry="same_idempotency_key_required",
        )

    def validate_public_result(self, value: Any) -> bool:
        return self.public_result_validator(self.action_id, value)
