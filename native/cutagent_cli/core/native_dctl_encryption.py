"""Native DaVinci Resolve 21.1 DCTL encryption with exact artifact handling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

from ..errors import APICallFailed, CapabilityNegotiationFailed, ValidationError
from .resolve_api_version import at_least


@dataclass(frozen=True)
class DCTLEncryptionRequest:
    input_path: Path
    output_path: Path
    expiry: str | None
    overwrite: bool


def _normalize_expiry(expiry: str | None) -> str | None:
    if expiry is None:
        return None
    value = str(expiry).strip()
    if not value:
        return None
    parse_value = f"{value[:-1]}+00:00" if value.endswith(("Z", "z")) else value
    try:
        if "T" in parse_value or " " in parse_value:
            datetime.fromisoformat(parse_value)
        else:
            date.fromisoformat(parse_value)
    except ValueError as exc:
        raise ValidationError(
            "DCTL encryption expiry must be a valid ISO 8601 date or datetime.",
            details={"expiry": value},
        ) from exc
    return value


def prepare_encrypt_dctl_request(
    input_path: str,
    output_path: str,
    *,
    expiry: str | None = None,
    overwrite: bool = False,
) -> DCTLEncryptionRequest:
    source = Path(str(input_path or "")).expanduser()
    target = Path(str(output_path or "")).expanduser()
    if not str(input_path or "").strip() or not str(output_path or "").strip():
        raise ValidationError("DCTL encryption requires nonempty input and output paths.")
    if source.is_symlink():
        raise ValidationError("DCTL encryption input must not be a symbolic link.", details={"path": str(source)})
    try:
        source = source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValidationError("DCTL encryption input file does not exist.", details={"path": str(source)}) from exc
    if not source.is_file() or source.suffix.lower() != ".dctl":
        raise ValidationError("DCTL encryption input must be a regular .dctl file.", details={"path": str(source)})

    try:
        parent = target.parent.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValidationError(
            "DCTL encryption output folder does not exist.", details={"path": str(target.parent)}
        ) from exc
    target = parent / target.name
    if not parent.is_dir() or target.suffix.lower() != ".dctle":
        raise ValidationError(
            "DCTL encryption output must be an exact .dctle file path in an existing folder.",
            details={"path": str(target)},
        )
    if target == source:
        raise ValidationError("DCTL encryption output must differ from the source file.")
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValidationError("DCTL encryption output must be a regular file path.", details={"path": str(target)})
    if target.exists() and not overwrite:
        raise ValidationError(
            "DCTL encryption output already exists; pass --overwrite to replace it.",
            details={"path": str(target)},
        )
    return DCTLEncryptionRequest(source, target, _normalize_expiry(expiry), bool(overwrite))


def _generated_artifact(staging: Path) -> Path:
    entries = list(staging.iterdir())
    if len(entries) != 1:
        raise APICallFailed(
            "DaVinci Resolve did not create exactly one encrypted DCTL artifact.",
            details={"artifact_count": len(entries)},
        )
    artifact = entries[0]
    artifact_stat = os.lstat(artifact)
    if not stat.S_ISREG(artifact_stat.st_mode) or artifact_stat.st_size < 1:
        raise APICallFailed("DaVinci Resolve created an invalid encrypted DCTL artifact.")
    return artifact


def _open_exclusive_target(target: Path, flags: int) -> int:
    return os.open(target, flags, 0o600)


def _install_artifact(artifact: Path, request: DCTLEncryptionRequest) -> None:
    target = request.output_path
    if request.overwrite:
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValidationError("DCTL encryption output is no longer a replaceable regular file.")
        os.replace(artifact, target)
        return
    try:
        os.link(artifact, target)
    except FileExistsError as exc:
        raise ValidationError(
            "DCTL encryption output was created by another process and was not replaced.",
            details={"path": str(target)},
        ) from exc
    except OSError:
        # FAT/exFAT and some managed volumes do not support hard links. An
        # exclusive destination still preserves the no-clobber guarantee.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_BINARY", 0)
        descriptor: int | None = None
        owned_stat: os.stat_result | None = None
        try:
            descriptor = _open_exclusive_target(target, flags)
            owned_stat = os.fstat(descriptor)
            with artifact.open("rb") as source, os.fdopen(descriptor, "wb") as destination:
                descriptor = None
                shutil.copyfileobj(source, destination, length=1024 * 1024)
                destination.flush()
                os.fsync(destination.fileno())
        except FileExistsError as exc:
            raise ValidationError(
                "DCTL encryption output was created by another process and was not replaced.",
                details={"path": str(target)},
            ) from exc
        except OSError as exc:
            try:
                current_stat = os.lstat(target)
            except OSError:
                current_stat = None
            if owned_stat is not None and current_stat is not None and os.path.samestat(owned_stat, current_stat):
                target.unlink(missing_ok=True)
            raise APICallFailed("Encrypted DCTL artifact could not be installed at the requested path.") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
    artifact.unlink()


def encrypt_dctl(conn: Any, request: DCTLEncryptionRequest) -> dict[str, Any]:
    product_getter = getattr(getattr(conn, "resolve", None), "GetProductName", None)
    product = product_getter() if callable(product_getter) else None
    if not at_least(conn, 21, 1) or not isinstance(product, str) or "Studio" not in product:
        raise CapabilityNegotiationFailed("Native DCTL encryption requires DaVinci Resolve Studio 21.1 or newer.")
    encrypt = getattr(conn.resolve, "EncryptDCTL", None)
    if not callable(encrypt):
        raise CapabilityNegotiationFailed("Native DCTL encryption is unavailable in this DaVinci Resolve runtime.")

    with tempfile.TemporaryDirectory(prefix=".cutagent-dctl-encrypt-", dir=request.output_path.parent) as folder:
        staging = Path(folder)
        options: dict[str, str] = {
            "Name": request.output_path.name,
            "OutputFolder": str(staging),
        }
        if request.expiry is not None:
            options["Expiry"] = request.expiry
        try:
            succeeded = encrypt(str(request.input_path), options)
        except Exception as exc:
            raise APICallFailed("DaVinci Resolve failed while encrypting the DCTL artifact.") from exc
        if succeeded is not True:
            raise APICallFailed("DaVinci Resolve rejected the DCTL encryption request.")
        artifact = _generated_artifact(staging)
        _install_artifact(artifact, request)

    size = request.output_path.stat().st_size
    hasher = hashlib.sha256()
    with request.output_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    return {
        "input_path": str(request.input_path),
        "output_path": str(request.output_path),
        "expiry": request.expiry,
        "overwrite": request.overwrite,
        "size_bytes": size,
        "sha256": digest,
        "route": "api_native_encrypt_dctl",
    }
