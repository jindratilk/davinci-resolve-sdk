from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutagent_cli.errors import ValidationError
from cutagent_cli.private_sdk_descriptors import project_preset_export_prepared_action as module


class Project:
    def __init__(self, content: bytes = b"project preset bytes"):
        self.content = content
        self.export_ack = True
        self.export_calls = 0
        self.settings = {"timelineFrameRate": "24"}
        self.presets = [{"Name": "Editorial", "Width": 1920, "Height": 1080}]

    def GetUniqueId(self): return "native-project"
    def GetName(self): return "Current Project"
    def GetRenderJobList(self): return []
    def GetSetting(self): return dict(self.settings)
    def GetProjectSettingsPresetList(self): return list(self.presets)
    def ExportProjectSettingsPreset(self, name, path):
        self.export_calls += 1
        assert name == "Editorial"
        Path(path).write_bytes(self.content)
        return self.export_ack


class Timeline:
    def GetName(self): return "Timeline 1"
    def GetUniqueId(self): return "native-timeline"


class ProjectManager:
    def GetCurrentDatabase(self): return {"DbType": "Disk", "DbName": "Local"}


def descriptor():
    return module.ProjectPresetExportDescriptor(
        managed_artifact_path=lambda context, artifact_id, **_kwargs: context["privateBindings"]["privateManagedArtifacts"][artifact_id]["path"],
        signed_artifact_targets=lambda _context, project, artifact_id: [project, {"kind": "artifact", "stableId": artifact_id, "revision": "revision-artifact"}],
        specific_impact=lambda _context, action_id, _value, targets: {"actionId": action_id, "targets": targets},
        project_result_builder=lambda action_id, **kwargs: {"actionId": action_id, "payload": kwargs},
        public_result_validator=lambda action_id, value: value.get("actionId") == action_id,
    )


def setup(tmp_path, monkeypatch):
    project = Project()
    resolve = SimpleNamespace(GetCurrentPage=lambda: "edit")
    connection = SimpleNamespace(project=project, timeline=Timeline(), project_manager=ProjectManager(), resolve=resolve)
    monkeypatch.setattr(module, "get_connection", lambda **_kwargs: connection)
    store = tmp_path / "managed"
    store.mkdir(mode=0o700)
    reservation = store / "artifact_project_preset.preset"
    descriptor_fd = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(descriptor_fd)
    observed = reservation.lstat()
    artifact_id = "artifact_project_preset"
    context = {
        "mutationBase": {"operationId": "operation_project_preset_export"},
        "project": {
            "projectLibraryId": "project-library",
            "projectId": "project-current",
            "projectRevision": "revision-project",
            "nativeProjectId": "native-project",
            "nativeProjectLibrary": {"name": "Local", "kind": "disk"},
        },
        "privateBindings": {
            "privateArtifactStoreRoot": str(store),
            "privateManagedArtifacts": {
                artifact_id: {
                    "path": str(reservation),
                    "reservationId": "operation_project_preset_export",
                    "reservationIdentity": {"device": observed.st_dev, "inode": observed.st_ino},
                }
            },
        },
    }
    return project, reservation, context, {"name": "Editorial", "destinationArtifactId": artifact_id}


def test_project_preset_export_preserves_reservation_inode_and_returns_path_free_receipt(tmp_path, monkeypatch):
    project, reservation, context, value = setup(tmp_path, monkeypatch)
    owner = descriptor()
    prepared = owner.prepare(context, owner.validate_input(value))
    before = reservation.lstat()
    result = owner.execute(context, prepared)

    assert reservation.read_bytes() == project.content
    assert os.path.samestat(before, reservation.lstat())
    assert result == {"artifact": {
        "artifactId": value["destinationArtifactId"],
        "mediaType": "application/octet-stream",
        "byteCount": len(project.content),
        "sha256": "sha256:a7440d7d9f8eb7934c4078577270802633707d16762d20b9df333211bc3dae2e",
    }}
    assert owner.verify(context, prepared, result)["outcome"] == "passed"
    public = owner.project_result(context, prepared, result)
    assert public["payload"]["target"] == {"name": "Editorial"}
    assert public["payload"]["data"] == result
    assert str(reservation) not in repr(public)


def test_project_preset_export_rejects_replaced_reservation_without_touching_replacement(tmp_path, monkeypatch):
    project, reservation, context, value = setup(tmp_path, monkeypatch)
    owner = descriptor()
    prepared = owner.prepare(context, owner.validate_input(value))
    reservation.unlink()
    replacement = b"external replacement"
    reservation.write_bytes(replacement)
    reservation.chmod(0o600)

    with pytest.raises(ValidationError, match="identity changed"):
        owner.execute(context, prepared)
    assert project.export_calls == 0
    assert reservation.read_bytes() == replacement
    recovery = owner.recover(context, prepared, RuntimeError("failed"))
    assert recovery == {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}
    assert reservation.read_bytes() == replacement


def test_project_preset_export_rejects_another_operations_reservation_without_touching_it(tmp_path, monkeypatch):
    _project, reservation, context, value = setup(tmp_path, monkeypatch)
    reservation.write_bytes(b"other operation")
    context["privateBindings"]["privateManagedArtifacts"][value["destinationArtifactId"]]["reservationId"] = "operation_other"

    with pytest.raises(ValidationError, match="custody is incomplete"):
        descriptor().prepare(context, value)
    assert reservation.read_bytes() == b"other operation"


def test_project_preset_export_partial_write_is_truncated_on_owned_inode(tmp_path, monkeypatch):
    _project, reservation, context, value = setup(tmp_path, monkeypatch)
    owner = descriptor()
    prepared = owner.prepare(context, owner.validate_input(value))
    real_write = module.os.write
    calls = 0

    def failing_write(fd, data):
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(fd, data[:4])
        raise OSError("injected write failure")

    monkeypatch.setattr(module.os, "write", failing_write)
    with pytest.raises(OSError, match="injected write failure"):
        owner.execute(context, prepared)
    assert reservation.read_bytes() == b""
    assert owner.recover(context, prepared, RuntimeError("failed")) == {
        "outcome": "succeeded", "attempted": False, "manualActionRequired": False,
    }


def test_project_preset_export_rejects_growing_staging_and_malformed_inode_custody(tmp_path, monkeypatch):
    _project, reservation, context, value = setup(tmp_path, monkeypatch)
    owner = descriptor()
    malformed = dict(context)
    malformed["privateBindings"] = dict(context["privateBindings"])
    malformed["privateBindings"]["privateManagedArtifacts"] = {
        value["destinationArtifactId"]: {
            **context["privateBindings"]["privateManagedArtifacts"][value["destinationArtifactId"]],
            "reservationIdentity": {"device": True, "inode": reservation.lstat().st_ino},
        }
    }
    with pytest.raises(ValidationError, match="custody is incomplete"):
        owner.prepare(malformed, owner.validate_input(value))

    prepared = owner.prepare(context, owner.validate_input(value))
    real_read = module.os.read
    reads = 0

    def growing_read(fd, size):
        nonlocal reads
        reads += 1
        if reads == 2:
            return b"x"
        return real_read(fd, size)

    monkeypatch.setattr(module.os, "read", growing_read)
    with pytest.raises(module.APICallFailed, match="grew"):
        owner.execute(context, prepared)
    assert reservation.read_bytes() == b""


@pytest.mark.parametrize("drift", ["timeline", "page"])
def test_project_preset_export_detects_exact_context_drift(tmp_path, monkeypatch, drift):
    _project, _reservation, context, value = setup(tmp_path, monkeypatch)
    owner = descriptor()
    prepared = owner.prepare(context, owner.validate_input(value))
    result = owner.execute(context, prepared)
    connection = module.get_connection()
    if drift == "timeline":
        connection.timeline = SimpleNamespace(
            GetName=lambda: "Timeline 1",
            GetUniqueId=lambda: "native-timeline-other",
        )
    else:
        connection.resolve.GetCurrentPage = lambda: "deliver"
    verified = owner.verify(context, prepared, result)
    assert verified["outcome"] == "failed"
    assert verified["protectedStatePreserved"] is False


def test_project_preset_export_allows_no_current_timeline_and_rejects_nonliteral_native_ack(tmp_path, monkeypatch):
    project, reservation, context, value = setup(tmp_path, monkeypatch)
    connection = module.get_connection()
    connection.timeline = None
    owner = descriptor()
    prepared = owner.prepare(context, owner.validate_input(value))
    assert prepared["preState"]["timelineNativeId"] is None

    project.export_ack = 1
    with pytest.raises(module.APICallFailed, match="rejected"):
        owner.execute(context, prepared)
    assert reservation.read_bytes() == b""
