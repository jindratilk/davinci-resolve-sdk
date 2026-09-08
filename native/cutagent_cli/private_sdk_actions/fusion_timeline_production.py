"""Production contribution factory for Fusion and residual Timeline/Version.

The public request carries only stable IDs and revisions.  Exact native item,
artifact, reservation, and filesystem custody remains in the signed runtime's
deep-frozen ``privateBindings`` context.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import struct
from types import MappingProxyType
from typing import Any, Mapping

from .fusion_prepared_action import fusion_prepared_action_descriptors
from .fusion_runtime import FusionPreparedActionRuntime
from ..private_sdk_descriptors.timeline_version_prepared_action import (
    TIMELINE_VERSION_CALLABLE_ACTION_IDS,
    timeline_version_prepared_action_production_contribution,
)


FUSION_ARTIFACT_BACKED_ACTION_IDS = frozenset({
    "cutagent.action.dctl.apply", "cutagent.action.fusion.generate",
    "cutagent.action.fusion.image.set", "cutagent.action.fusion.insert_setting",
    "cutagent.action.fusion.setting.inspect", "cutagent.action.fusion.setting.summary",
    "cutagent.action.fusion.setting.validate", "cutagent.action.fusion.template.assets.add",
    "cutagent.action.fusion.template.assets.list", "cutagent.action.fusion.template.apply",
    "cutagent.action.fusion.template.dir",
    "cutagent.action.fusion.template.icon.set", "cutagent.action.fusion.template.install",
    "cutagent.action.fusion.template.package_drfx", "cutagent.action.fusion.template.scaffold",
    "cutagent.action.fusion.template.show", "cutagent.action.fusion.template.uninstall",
    "cutagent.action.fusion.template.validate", "cutagent.action.lut.convert",
    "cutagent.action.lut.generate.identity", "cutagent.action.lut.inspect",
    "cutagent.action.lut.install", "cutagent.action.lut.list", "cutagent.action.lut.remove",
    "cutagent.action.lut.validate",
})


def _managed_artifact_identity(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Fusion managed-artifact {label} is malformed.")
    identity: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            encoded = item.get("$cutagentFloat64")
            if set(item) != {"$cutagentFloat64"} or not isinstance(encoded, str) \
                    or re.fullmatch(r"[a-f0-9]{16}", encoded) is None:
                raise ValueError(f"Fusion managed-artifact {label} is malformed.")
            item = struct.unpack(">d", bytes.fromhex(encoded))[0]
            if not math.isfinite(item):
                raise ValueError(f"Fusion managed-artifact {label} is malformed.")
        elif isinstance(item, (list, tuple)):
            raise ValueError(f"Fusion managed-artifact {label} is malformed.")
        identity[str(key)] = item
    return identity


def _managed_artifact_rows(value: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"Fusion managed-artifact {label} is malformed.")
    rows: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError(f"Fusion managed-artifact {label} is malformed.")
        row = dict(raw)
        if "identity" in row:
            row["identity"] = _managed_artifact_identity(
                row["identity"], label=f"{label} identity"
            )
        if any(
            isinstance(item, (Mapping, list, tuple))
            for key, item in row.items()
            if key != "identity"
        ):
            raise ValueError(f"Fusion managed-artifact {label} is malformed.")
        rows.append(row)
    return rows


def _managed_artifact_record(value: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(value)
    for key in ("identity", "reservationIdentity"):
        if key in record:
            record[key] = _managed_artifact_identity(record[key], label=key)
    for key in ("entries", "directoryEntries"):
        if key in record:
            record[key] = _managed_artifact_rows(record[key], label=key)
    if "directories" in record:
        directories = record["directories"]
        if not isinstance(directories, (list, tuple)) or any(
            not isinstance(item, str) for item in directories
        ):
            raise ValueError("Fusion managed-artifact directories are malformed.")
        record["directories"] = list(directories)
    if any(
        isinstance(item, (Mapping, list, tuple))
        for key, item in record.items()
        if key not in {
            "identity", "reservationIdentity", "entries",
            "directoryEntries", "directories",
        }
    ):
        raise ValueError("Fusion managed-artifact record is malformed.")
    return record


class ProductionFusionPreparedActionRuntime(FusionPreparedActionRuntime):
    """Adapts carrier-owned private bindings without weakening fresh readback."""

    @staticmethod
    def _private_bindings(context: Mapping[str, Any]) -> Mapping[str, Any]:
        bindings = context.get("privateBindings")
        if bindings is None:
            return MappingProxyType({})
        if not isinstance(bindings, Mapping):
            raise ValueError("Fusion private binding custody is malformed.")
        return bindings

    def _bound(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        bindings = self._private_bindings(context)
        managed = bindings.get("privateManagedArtifacts", {})
        if not isinstance(managed, Mapping):
            raise ValueError("Fusion managed-artifact custody is malformed.")
        normalized_managed: dict[str, Any] = {}
        for artifact_id, raw in managed.items():
            if not isinstance(artifact_id, str) or not isinstance(raw, Mapping):
                raise ValueError("Fusion managed-artifact record is malformed.")
            record = _managed_artifact_record(raw)
            # The carrier owns an exclusive zero-byte placeholder for every
            # destination.  Existing runtime handlers may overwrite only this
            # exact reservation after the identity check below.
            if "reservationIdentity" in record:
                record["overwrite"] = True
            normalized_managed[artifact_id] = record
        mutation_base = context.get("mutationBase")
        return {
            **context,
            **bindings,
            "privateManagedArtifacts": normalized_managed,
            **({"mutationPolicy": mutation_base} if isinstance(mutation_base, Mapping) else {}),
            "_fusionArtifactCustody": self._custody,
        }

    @staticmethod
    def _assert_reservations(context: Mapping[str, Any]) -> None:
        records = context.get("privateManagedArtifacts")
        if not isinstance(records, Mapping):
            return
        for record in records.values():
            if not isinstance(record, Mapping) or "reservationIdentity" not in record:
                continue
            path_value = record.get("path")
            identity = record.get("reservationIdentity")
            if not isinstance(path_value, str) or not isinstance(identity, Mapping):
                raise ValueError("Fusion destination reservation is malformed.")
            path = Path(path_value)
            current = path.lstat()
            expected_device = identity.get("device")
            expected_inode = identity.get("inode")
            if (
                path.is_symlink()
                or not stat.S_ISREG(current.st_mode)
                or current.st_size != 0
                or current.st_dev != expected_device
                or current.st_ino != expected_inode
                or stat.S_IMODE(current.st_mode) & 0o077
            ):
                raise ValueError("Fusion destination reservation identity changed.")

    @staticmethod
    def _assert_managed_inputs(context: Mapping[str, Any]) -> None:
        records = context.get("privateManagedArtifacts")
        if not isinstance(records, Mapping):
            return
        for record in records.values():
            if not isinstance(record, Mapping) or "reservationIdentity" in record:
                continue
            path_value = record.get("path")
            identity = record.get("identity")
            if not isinstance(path_value, str) or not isinstance(identity, Mapping):
                raise ValueError("Fusion managed input identity is incomplete.")
            path = Path(path_value)
            current = path.lstat()
            if path.is_symlink() or current.st_dev != identity.get("device") or current.st_ino != identity.get("inode") \
                    or abs(current.st_mtime_ns / 1_000_000 - float(identity.get("mtimeMs", -1))) > 1 \
                    or abs(current.st_ctime_ns / 1_000_000 - float(identity.get("ctimeMs", -1))) > 1:
                raise ValueError("Fusion managed input identity changed.")
            if stat.S_ISREG(current.st_mode):
                expected = str(record.get("sha256") or "").removeprefix("sha256:")
                if not expected or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError("Fusion managed input bytes changed.")
            elif stat.S_ISDIR(current.st_mode):
                entries = record.get("entries")
                directories = record.get("directories")
                directory_entries = record.get("directoryEntries")
                if not isinstance(entries, (list, tuple)) or not isinstance(directories, (list, tuple)) \
                        or not isinstance(directory_entries, (list, tuple)):
                    raise ValueError("Fusion managed directory manifest is incomplete.")
                actual_files: set[str] = set()
                actual_directories: set[str] = set()
                for child in path.rglob("*"):
                    relative = child.relative_to(path).as_posix()
                    child_stat = child.lstat()
                    if child.is_symlink():
                        raise ValueError("Fusion managed directory content changed.")
                    if stat.S_ISREG(child_stat.st_mode):
                        actual_files.add(relative)
                    elif stat.S_ISDIR(child_stat.st_mode):
                        actual_directories.add(relative)
                    else:
                        raise ValueError("Fusion managed directory contains a special file.")
                if actual_files != {str(entry.get("relativePath")) for entry in entries} \
                        or actual_directories != set(map(str, directories)):
                    raise ValueError("Fusion managed directory hierarchy changed.")
                for directory_entry in directory_entries:
                    child = path / str(directory_entry.get("relativePath") or "")
                    expected_identity = directory_entry.get("identity") if isinstance(directory_entry, Mapping) else None
                    child_stat = child.lstat()
                    if not stat.S_ISDIR(child_stat.st_mode) or child.is_symlink() or not isinstance(expected_identity, Mapping) \
                            or child_stat.st_dev != expected_identity.get("device") or child_stat.st_ino != expected_identity.get("inode") \
                            or abs(child_stat.st_mtime_ns / 1_000_000 - float(expected_identity.get("mtimeMs", -1))) > 1 \
                            or abs(child_stat.st_ctime_ns / 1_000_000 - float(expected_identity.get("ctimeMs", -1))) > 1:
                        raise ValueError("Fusion managed directory identity changed.")
                for entry in entries:
                    child = path / str(entry.get("relativePath") or "")
                    child_identity = entry.get("identity") if isinstance(entry, Mapping) else None
                    child_stat = child.lstat()
                    if child.is_symlink() or not child.is_file() or not isinstance(child_identity, Mapping) \
                            or child_stat.st_dev != child_identity.get("device") or child_stat.st_ino != child_identity.get("inode") \
                            or child_stat.st_size != entry.get("sizeBytes") \
                            or abs(child_stat.st_mtime_ns / 1_000_000 - float(child_identity.get("mtimeMs", -1))) > 1 \
                            or abs(child_stat.st_ctime_ns / 1_000_000 - float(child_identity.get("ctimeMs", -1))) > 1 \
                            or hashlib.sha256(child.read_bytes()).hexdigest() != str(entry.get("sha256") or "").removeprefix("sha256:"):
                        raise ValueError("Fusion managed directory content changed.")
            else:
                raise ValueError("Fusion managed input is not a regular file or directory.")

    @staticmethod
    def _request_targets(context: Mapping[str, Any]) -> list[dict[str, str]]:
        binding = context.get("exactRequestBinding")
        identities = binding.get("identities") if isinstance(binding, Mapping) else None
        revisions = binding.get("revisions") if isinstance(binding, Mapping) else None
        target_ids = identities.get("targetIds") if isinstance(identities, Mapping) else None
        target_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
        target_kinds = context.get("fusionRequestTargetKinds")
        allowed_kinds = {
            "project_library", "project", "timeline", "track", "clip",
            "fusion_composition", "media", "marker", "runtime_setting",
        }
        if (
            not isinstance(target_ids, (list, tuple))
            or not target_ids
            or len(set(target_ids)) != len(target_ids)
            or not isinstance(target_revisions, Mapping)
            or set(target_revisions) != set(target_ids)
            or not isinstance(target_kinds, Mapping)
            or set(target_kinds) != set(target_ids)
            or any(target_kinds[target_id] not in allowed_kinds for target_id in target_ids)
        ):
            raise ValueError("Fusion exact request target binding is incomplete.")
        return [
            {
                "kind": str(target_kinds[target_id]),
                "stableId": str(target_id),
                "revision": str(target_revisions[target_id]),
            }
            for target_id in target_ids
        ]

    def inspect(
        self, context: Mapping[str, Any], command_id: str, value: Mapping[str, Any]
    ) -> dict[str, Any]:
        bound = self._bound(context)
        self._assert_managed_inputs(bound)
        self._assert_reservations(bound)
        observed = super().inspect(bound, command_id, value)
        pre_state = deepcopy(dict(observed["preState"]))
        for record in bound.get("privateManagedArtifacts", {}).values():
            if not isinstance(record, Mapping) or "reservationIdentity" not in record:
                continue
            path_value = record.get("path")
            if not isinstance(path_value, str):
                continue
            affected_key = f"affected_{hashlib.sha256(path_value.encode()).hexdigest()}"
            if affected_key in pre_state:
                absent = json.dumps(
                    {"absent": True}, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                pre_state[affected_key] = {
                    "kind": "absent",
                    "digest": f"sha256:{hashlib.sha256(absent).hexdigest()}",
                }
        # Native targets remain private but participate in the kernel's exact
        # pre-state comparison, so a changed graph/path/checkpoint cannot pass
        # merely because its stable public alias is unchanged.
        pre_state["__cutagentNativeTargets"] = deepcopy(list(observed["targets"]))
        return {
            **observed,
            "targets": self._request_targets(bound),
            "preState": pre_state,
        }

    def execute(
        self,
        context: Mapping[str, Any],
        command_id: str,
        value: Mapping[str, Any],
        prepared: Mapping[str, Any],
    ) -> dict[str, Any]:
        bound = self._bound(context)
        self._assert_managed_inputs(bound)
        self._assert_reservations(bound)
        return super().execute(bound, command_id, value, prepared)

    def verify(
        self,
        context: Mapping[str, Any],
        command_id: str,
        value: Mapping[str, Any],
        prepared: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        return super().verify(self._bound(context), command_id, value, prepared, result)


def fusion_timeline_production_contribution_packet() -> Any:
    """Return the frozen carrier packet without importing it at module load."""

    from ..prepared_action_contributions import PreparedActionContributionPacket

    fusion = fusion_prepared_action_descriptors(
        runtime=ProductionFusionPreparedActionRuntime()
    )
    from ..private_sdk_descriptors.timeline_topology_production import (
        timeline_topology_prepared_action_packet,
    )
    topology, topology_authorities = timeline_topology_prepared_action_packet()
    timeline_all = timeline_version_prepared_action_production_contribution()
    timeline = {
        action_id: topology.get(action_id, timeline_all[action_id])
        for action_id in TIMELINE_VERSION_CALLABLE_ACTION_IDS
    }
    descriptors = {**fusion, **timeline}
    expected_fusion = 64
    if len(fusion) != expected_fusion or len(timeline) != 57 or len(descriptors) != expected_fusion + 57:
        raise ValueError("Fusion/Timeline production packet activation gate drifted.")
    return PreparedActionContributionPacket(
        owner="fusion-timeline-version",
        descriptors=MappingProxyType(descriptors),
        execution_authorities=topology_authorities,
    )


__all__ = [
    "FUSION_ARTIFACT_BACKED_ACTION_IDS",
    "ProductionFusionPreparedActionRuntime",
    "fusion_timeline_production_contribution_packet",
]
