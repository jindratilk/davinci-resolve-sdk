"""Signed-in desktop broker client for hosted ElevenLabs voiceovers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import ssl
import tempfile
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import certifi

from ..errors import APICallFailed, AuthorizationError, ValidationError
from ..machine_error_registry import apply_forwarded_error_contract, normalize_forwarded_error_code


_BROKER_URL_ENV = "CUTAGENT_CLI_BROKER_URL"
_BROKER_TOKEN_ENV = "CUTAGENT_CLI_BROKER_TOKEN"
_BROKER_CAPABILITY_ENV = "CUTAGENT_CLI_BROKER_CAPABILITY"
_BROKER_TOKEN_HEADER = "x-cutagent-cli-broker-token"
_BRIDGE_CAPABILITY_HEADER = "x-cutagent-bridge-capability"
_BROKER_TIMEOUT_SECONDS = 12 * 60
_DOWNLOAD_MAX_BYTES = 128 * 1024 * 1024


class _NoRedirectHandler(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


def _tls_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


_NO_REDIRECT_OPENER = urllib_request.build_opener(
    urllib_request.HTTPSHandler(context=_tls_context()),
    _NoRedirectHandler(),
)


def _required_broker_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise AuthorizationError(
        "ElevenLabs voiceover requires the signed-in CutAgent desktop app.",
        code="AUTH_REQUIRED",
        details={"required_runtime": "cutagent_desktop_broker"},
    )


def broker_request(payload: dict[str, Any]) -> dict[str, Any]:
    url = _required_broker_env(_BROKER_URL_ENV)
    token = _required_broker_env(_BROKER_TOKEN_ENV)
    capability = _required_broker_env(_BROKER_CAPABILITY_ENV)
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "content-type": "application/json",
            _BROKER_TOKEN_HEADER: token,
            _BRIDGE_CAPABILITY_HEADER: capability,
        },
    )
    try:
        with urllib_request.urlopen(
            request,
            timeout=_BROKER_TIMEOUT_SECONDS,
            context=_tls_context(),
        ) as response:
            response_body = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        try:
            error_payload = json.loads(response_body)
        except json.JSONDecodeError:
            error_payload = None
        broker_error = error_payload.get("error", {}) if isinstance(error_payload, dict) else {}
        error_code = broker_error.get("code") if isinstance(broker_error, dict) else None
        message = broker_error.get("message") if isinstance(broker_error, dict) else None
        details = broker_error.get("details") if isinstance(broker_error, dict) else None
        if exc.code in {401, 402, 403}:
            raise AuthorizationError(
                message or "CutAgent rejected the ElevenLabs voiceover request.",
                code=normalize_forwarded_error_code(
                    error_code,
                    fallback="AUTH_REQUIRED",
                    expected_exit_code=2,
                    expected_retryability="manual",
                ),
                details=details if isinstance(details, dict) else None,
            ) from exc
        failure = APICallFailed(
            message or f"ElevenLabs voiceover request failed with HTTP {exc.code}.",
            details={
                **(details if isinstance(details, dict) else {}),
                "status": exc.code,
                "broker_error_code": error_code,
            },
        )
        raise apply_forwarded_error_contract(failure, error_code, fallback="API_CALL_FAILED") from exc
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        raise APICallFailed(
            "Could not reach the CutAgent desktop voiceover broker.",
            details={"reason": str(exc)},
        ) from exc

    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise APICallFailed("CutAgent returned an invalid voiceover response.") from exc
    if not isinstance(parsed, dict) or parsed.get("ok") is not True:
        error_payload = parsed.get("error") if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict) else {}
        failure = APICallFailed(
            str(error_payload.get("message") or "ElevenLabs voiceover request failed."),
            details={"broker_error_code": error_payload.get("code")},
        )
        error_code = error_payload.get("code")
        raise apply_forwarded_error_contract(failure, error_code, fallback="API_CALL_FAILED")
    data = parsed.get("data")
    if not isinstance(data, dict):
        raise APICallFailed("CutAgent returned voiceover data in an invalid format.")
    return data


def _validate_audio_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urllib_parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname.endswith(".r2.cloudflarestorage.com"):
        raise APICallFailed("CutAgent returned an untrusted voiceover download URL.")
    return url


@dataclass
class OutputReservation:
    fd: int
    device: int
    inode: int


def prepare_output_path(output_path: str, *, force: bool) -> tuple[Path, OutputReservation | None]:
    destination = Path(output_path).expanduser().resolve(strict=False)
    if destination.exists() and not destination.is_file():
        raise ValidationError("Voiceover output must be a regular file path.", details={"path": str(destination)})
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        raise ValidationError(
            "Voiceover output already exists. Use --force to replace it.",
            details={"path": str(destination)},
        )
    if force:
        try:
            fd, temporary_path = tempfile.mkstemp(
                prefix=f".{destination.name}.", suffix=".preflight", dir=str(destination.parent)
            )
            os.close(fd)
            os.unlink(temporary_path)
        except OSError as exc:
            raise ValidationError(
                "Voiceover output cannot be written safely.",
                details={"path": str(destination), "reason": str(exc)},
            ) from exc
        return destination, None
    try:
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValidationError(
            "Voiceover output already exists. Use --force to replace it.",
            details={"path": str(destination)},
        ) from exc
    stat = os.fstat(fd)
    return destination, OutputReservation(fd=fd, device=stat.st_dev, inode=stat.st_ino)


def _reservation_matches(destination: Path, reservation: OutputReservation) -> bool:
    try:
        stat = destination.stat(follow_symlinks=False)
    except OSError:
        return False
    return stat.st_dev == reservation.device and stat.st_ino == reservation.inode


def cleanup_reservation(destination: Path, reservation: OutputReservation | None) -> None:
    if reservation is None:
        return
    matches = _reservation_matches(destination, reservation)
    if reservation.fd >= 0:
        try:
            os.close(reservation.fd)
        except OSError:
            pass
        reservation.fd = -1
    if matches:
        try:
            destination.unlink()
        except OSError:
            pass


def _stream_audio(handle: Any, response: Any) -> int:
    content_type = str(response.headers.get("content-type") or "").lower()
    if content_type and not content_type.startswith("audio/") and content_type != "application/octet-stream":
        raise APICallFailed("Generated voiceover download returned an unexpected content type.")
    try:
        content_length = int(response.headers.get("content-length") or 0)
    except (TypeError, ValueError):
        content_length = 0
    if content_length > _DOWNLOAD_MAX_BYTES:
        raise APICallFailed("Generated voiceover exceeds the 128 MB download limit.")
    received = 0
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        received += len(chunk)
        if received > _DOWNLOAD_MAX_BYTES:
            raise APICallFailed("Generated voiceover exceeds the 128 MB download limit.")
        handle.write(chunk)
    if received == 0:
        raise APICallFailed("Generated voiceover download was empty.")
    handle.flush()
    os.fsync(handle.fileno())
    return received


def download_audio(
    audio_url: Any,
    destination: Path,
    reservation: OutputReservation | None,
) -> int:
    request = urllib_request.Request(_validate_audio_url(audio_url), headers={"accept": "audio/mpeg"})
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=_BROKER_TIMEOUT_SECONDS) as response:
            if reservation is not None:
                if not _reservation_matches(destination, reservation):
                    raise ValidationError(
                        "Voiceover output changed while generation was running.",
                        details={"path": str(destination)},
                    )
                with os.fdopen(reservation.fd, "wb", closefd=True) as handle:
                    reservation.fd = -1
                    return _stream_audio(handle, response)
            fd, temporary_path = tempfile.mkstemp(
                prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
            )
            try:
                with os.fdopen(fd, "wb", closefd=True) as handle:
                    size_bytes = _stream_audio(handle, response)
                os.chmod(temporary_path, 0o600)
                os.replace(temporary_path, destination)
                return size_bytes
            except Exception:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
                raise
    except urllib_error.HTTPError as exc:
        raise APICallFailed(
            f"Generated voiceover download failed with HTTP {exc.code}.",
            details={"status": exc.code},
        ) from exc
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        raise APICallFailed(
            "Could not download the generated voiceover.",
            details={"reason": str(exc)},
        ) from exc
