"""Fresh filesystem identity checks for the assigned Fairlight action slice."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from .fairlight_runtime_projection_support import FairlightDescriptorError

ArtifactRole = Literal["input", "output"]
_REQUIREMENTS: dict[tuple[str, str], ArtifactRole] = {
    ("fairlight.bounce.mix_to_track", "outputPath"): "output",
    ("fairlight.bounce.track", "outputPath"): "output",
    ("fairlight.export.audio", "outputPath"): "output",
    ("fairlight.insert", "mediaPath"): "input",
    ("fairlight.sound_library.index_file", "path"): "input",
    ("fairlight.sound_library.index_folder", "folder"): "input",
    ("fairlight.sound_library.source_rebuild", "folder"): "input",
    ("fairlight.sound_library.source_remove", "sourcePath"): "input",
}
_CHUNK_SIZE = 1024 * 1024
_MAX_DIRECTORY_ENTRIES = 10_000


def fairlight_artifact_role(command_id: str, field: str) -> ArtifactRole | None:
    """Return this slice's exact role, leaving unrelated optional paths alone."""

    return _REQUIREMENTS.get((command_id, field))


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _directory_digest(path: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    entry_count = 0
    size_bytes = 0
    for candidate in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
        entry_count += 1
        if entry_count > _MAX_DIRECTORY_ENTRIES:
            raise FairlightDescriptorError(
                "VALIDATION_ERROR",
                "Fairlight managed directory exceeds the bounded identity scan",
            )
        if candidate.is_symlink():
            raise FairlightDescriptorError(
                "VALIDATION_ERROR",
                "Fairlight managed artifact identity does not follow symlinks",
            )
        relative = candidate.relative_to(path).as_posix().encode("utf-8")
        if candidate.is_dir():
            digest.update(b"D\0" + relative + b"\0")
            continue
        if not candidate.is_file():
            raise FairlightDescriptorError(
                "VALIDATION_ERROR",
                "Fairlight managed directory contains a non-file entry",
            )
        stat = candidate.stat()
        digest.update(
            b"F\0"
            + relative
            + b"\0"
            + _file_digest(candidate).encode("ascii")
            + b"\0"
        )
        size_bytes += stat.st_size
    return f"sha256:{digest.hexdigest()}", entry_count, size_bytes


def observe_managed_artifact(path: str | Path, *, allow_missing: bool) -> dict[str, Any]:
    """Read canonical identity from the live filesystem, never carrier values."""

    supplied = Path(path).expanduser()
    if not supplied.is_absolute():
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Fairlight managed artifact path is not absolute"
        )
    if supplied.is_symlink():
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Fairlight managed artifact must not be a symlink"
        )
    candidate = supplied.resolve(strict=False)
    if not candidate.exists():
        if allow_missing:
            return {
                "path": str(candidate),
                "exists": False,
                "kind": "missing",
                "sizeBytes": 0,
                "mtimeNs": None,
                "contentSha256": None,
                "entryCount": None,
            }
        raise FairlightDescriptorError(
            "READINESS_FAILED", "Required Fairlight managed artifact does not exist"
        )
    stat = candidate.stat()
    if candidate.is_file():
        content_digest = _file_digest(candidate)
        entry_count = None
        size_bytes = stat.st_size
        kind = "file"
    elif candidate.is_dir():
        content_digest, entry_count, size_bytes = _directory_digest(candidate)
        kind = "directory"
    else:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Fairlight managed artifact has an unsupported type"
        )
    return {
        "path": str(candidate),
        "exists": True,
        "kind": kind,
        "sizeBytes": size_bytes,
        "mtimeNs": stat.st_mtime_ns,
        "contentSha256": content_digest,
        "entryCount": entry_count,
    }


def capture_fairlight_artifact_identity(
    command_id: str, field: str, path: str | Path
) -> dict[str, Any] | None:
    """Capture pre-execution identity, or ``None`` for an unowned field."""

    role = fairlight_artifact_role(command_id, field)
    if role is None:
        return None
    observed = observe_managed_artifact(path, allow_missing=role == "output")
    return {"commandId": command_id, "field": field, "role": role, **observed}


def validate_fresh_fairlight_artifact(
    before: dict[str, Any], path: str | Path
) -> dict[str, Any]:
    """Prove an input stayed unchanged or an output was freshly materialized."""

    keys = {
        "commandId", "field", "role", "path", "exists", "kind", "sizeBytes",
        "mtimeNs", "contentSha256", "entryCount",
    }
    if not isinstance(before, dict) or set(before) != keys:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Fairlight artifact baseline is malformed"
        )
    role = fairlight_artifact_role(before["commandId"], before["field"])
    if role != before["role"]:
        raise FairlightDescriptorError(
            "VALIDATION_ERROR", "Fairlight artifact baseline role is invalid"
        )
    after = observe_managed_artifact(path, allow_missing=False)
    if after["path"] != before["path"]:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight artifact path changed after admission"
        )
    if role == "input":
        comparable = ("kind", "sizeBytes", "contentSha256", "entryCount")
        if any(after[key] != before[key] for key in comparable):
            raise FairlightDescriptorError(
                "VERIFICATION_FAILED",
                "Fairlight input artifact content changed during execution",
            )
    elif after["kind"] != "file" or after["sizeBytes"] <= 0:
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Fairlight output artifact is not a non-empty regular file",
        )
    elif (
        before["exists"]
        and before["contentSha256"] == after["contentSha256"]
        and before["sizeBytes"] == after["sizeBytes"]
    ):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED",
            "Fairlight output content did not change during execution",
        )
    return {
        "commandId": before["commandId"],
        "field": before["field"],
        "role": role,
        **after,
    }


def artifact_evidence_digest(identity: dict[str, Any]) -> str:
    digest = identity.get("contentSha256") if isinstance(identity, dict) else None
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise FairlightDescriptorError(
            "VERIFICATION_FAILED", "Fairlight content identity digest is unavailable"
        )
    return digest
