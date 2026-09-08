"""Hosted transcript commands brokered by the signed-in CutAgent desktop app."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import uuid
from typing import Any, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

import typer

from ..connection import get_connection
from ..errors import APICallFailed, AuthorizationError, ValidationError, handle_errors
from ..machine_error_registry import apply_forwarded_error_contract, normalize_forwarded_error_code
from ..output import (
    dry_run_message,
    is_dry_run,
    output,
    set_capability_context,
    set_execution_engine,
    set_verification_status,
)
from ..policy import enforce_mutation_policy


app = typer.Typer(help="Hosted transcript generation through the signed-in CutAgent app.")

_BROKER_URL_ENV = "CUTAGENT_CLI_BROKER_URL"
_BROKER_TOKEN_ENV = "CUTAGENT_CLI_BROKER_TOKEN"
_BROKER_CAPABILITY_ENV = "CUTAGENT_CLI_BROKER_CAPABILITY"
_BROKER_TOKEN_HEADER = "x-cutagent-cli-broker-token"
_BRIDGE_CAPABILITY_HEADER = "x-cutagent-bridge-capability"
_BROKER_TIMEOUT_SECONDS = 50 * 60


def _required_broker_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    raise AuthorizationError(
        "Hosted transcript generation requires the signed-in CutAgent desktop app.",
        code="AUTH_REQUIRED",
        details={"required_runtime": "cutagent_desktop_broker"},
    )


def _broker_call(payload: dict[str, Any], *, bridge_capability: Optional[str] = None) -> dict[str, Any]:
    url = _required_broker_env(_BROKER_URL_ENV)
    token = _required_broker_env(_BROKER_TOKEN_ENV)
    capability = bridge_capability.strip() if isinstance(bridge_capability, str) else ""
    if not capability:
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
        with urllib_request.urlopen(request, timeout=_BROKER_TIMEOUT_SECONDS) as response:
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
        error_details = broker_error.get("details") if isinstance(broker_error, dict) else None
        suggested_fix = broker_error.get("suggested_fix") if isinstance(broker_error, dict) else None
        if exc.code in {401, 403}:
            raise AuthorizationError(
                message or "CutAgent rejected the hosted transcript request.",
                code=normalize_forwarded_error_code(
                    error_code,
                    fallback="AUTH_REQUIRED",
                    expected_exit_code=2,
                    expected_retryability="manual",
                ),
                details=error_details if isinstance(error_details, dict) else None,
            ) from exc
        failure = APICallFailed(
            message or f"Hosted transcript request failed with HTTP {exc.code}.",
            details={
                **(error_details if isinstance(error_details, dict) else {}),
                "status": exc.code,
                "broker_error_code": error_code,
            },
            suggested_fix=suggested_fix if isinstance(suggested_fix, str) else None,
        )
        raise apply_forwarded_error_contract(failure, error_code, fallback="API_CALL_FAILED") from exc
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        raise APICallFailed(
            "Could not reach the CutAgent desktop transcript broker.",
            details={"reason": str(exc)},
        ) from exc

    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise APICallFailed("CutAgent returned an invalid transcript response.") from exc
    if not isinstance(parsed, dict):
        raise APICallFailed("CutAgent returned an invalid transcript response.")
    if parsed.get("ok") is not True:
        error_payload = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
        error_code = error_payload.get("code")
        error_details = error_payload.get("details")
        failure = APICallFailed(
            str(error_payload.get("message") or "Hosted transcript generation failed."),
            details={
                **(error_details if isinstance(error_details, dict) else {}),
                "broker_error_code": error_code,
            },
        )
        raise apply_forwarded_error_contract(failure, error_code, fallback="API_CALL_FAILED")
    data = parsed.get("data")
    if not isinstance(data, dict):
        raise APICallFailed("CutAgent returned an invalid transcript response.")
    return data


def _broker_request(payload: dict[str, Any]) -> dict[str, Any]:
    data = _broker_call(payload)
    if isinstance(data.get("transcript"), dict):
        return data
    if (
        data.get("delivery_status") == "acknowledged"
        and isinstance(data.get("output_sha256"), str)
        and len(data["output_sha256"]) == 64
        and all(character in "0123456789abcdefABCDEF" for character in data["output_sha256"])
    ):
        return data
    else:
        raise APICallFailed("CutAgent returned a transcript response without transcript data.")


def _broker_ack(delivery_id: str, bridge_capability: str, output_sha256: str) -> None:
    data = _broker_call(
        {
            "acknowledge_delivery_id": delivery_id,
            "output_sha256": output_sha256,
        },
        bridge_capability=bridge_capability,
    )
    if data.get("acknowledged") is not True or data.get("delivery_id") != delivery_id:
        raise APICallFailed("CutAgent did not acknowledge the durable transcript delivery.")


def _resolve_output_path(output_path: str, *, force: bool) -> Path:
    destination = Path(output_path).expanduser().resolve(strict=False)
    if destination.exists() and not destination.is_file():
        raise ValidationError(
            "Transcript output must be a regular file path.",
            details={"path": str(destination)},
        )
    if destination.exists() and not force:
        raise ValidationError(
            "Transcript output already exists. Use --force to replace it.",
            details={"path": str(destination)},
        )
    return destination


def _preflight_atomic_replace(destination: Path) -> None:
    """Prove a forced output can create its atomic sibling before billing."""
    try:
        fd, temporary_path = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".preflight",
            dir=str(destination.parent),
        )
        os.close(fd)
        os.unlink(temporary_path)
    except OSError as exc:
        raise ValidationError(
            "Transcript output cannot be written safely.",
            details={"path": str(destination), "reason": str(exc)},
        ) from exc


@dataclass
class _OutputReservation:
    fd: int
    device: int
    inode: int


def _reserve_output_path(destination: Path) -> _OutputReservation:
    """Reserve a new destination before starting the account-billed request."""
    try:
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValidationError(
            "Transcript output already exists. Use --force to replace it.",
            details={"path": str(destination)},
        ) from exc
    stat = os.fstat(fd)
    reservation = _OutputReservation(fd=fd, device=stat.st_dev, inode=stat.st_ino)
    if os.name == "nt":
        # Python's Windows file handle does not share delete access. Close the
        # placeholder so a competing replacement can occur and be detected by
        # the file identity check before writing.
        _close_reservation(reservation)
    return reservation


def _reservation_matches(destination: Path, reservation: _OutputReservation) -> bool:
    try:
        stat = destination.stat(follow_symlinks=False)
    except OSError:
        return False
    return stat.st_dev == reservation.device and stat.st_ino == reservation.inode


def _close_reservation(reservation: _OutputReservation) -> None:
    if reservation.fd < 0:
        return
    try:
        os.close(reservation.fd)
    except OSError:
        pass
    reservation.fd = -1


def _cleanup_reservation(destination: Path, reservation: _OutputReservation) -> None:
    matches = _reservation_matches(destination, reservation)
    _close_reservation(reservation)
    if matches:
        try:
            destination.unlink()
        except OSError:
            pass


def _fsync_parent_directory(destination: Path) -> None:
    try:
        directory_fd = os.open(destination.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    except OSError:
        # Some supported filesystems do not expose directory fsync.
        pass
    finally:
        os.close(directory_fd)


def _write_reserved_json(
    destination: Path,
    reservation: _OutputReservation,
    payload: dict[str, Any],
) -> Path:
    if not _reservation_matches(destination, reservation):
        _close_reservation(reservation)
        raise ValidationError(
            "Transcript output changed while the hosted request was running.",
            details={"path": str(destination)},
        )
    write_fd = reservation.fd
    if write_fd < 0:
        try:
            write_fd = os.open(destination, os.O_WRONLY)
        except OSError as exc:
            raise ValidationError(
                "Transcript output changed while the hosted request was running.",
                details={"path": str(destination)},
            ) from exc
        stat = os.fstat(write_fd)
        if stat.st_dev != reservation.device or stat.st_ino != reservation.inode:
            os.close(write_fd)
            raise ValidationError(
                "Transcript output changed while the hosted request was running.",
                details={"path": str(destination)},
            )
    try:
        with os.fdopen(write_fd, "w", encoding="utf-8", closefd=True) as handle:
            reservation.fd = -1
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        _cleanup_reservation(destination, reservation)
        raise
    if not _reservation_matches(destination, reservation):
        raise ValidationError(
            "Transcript output changed while the hosted request was running.",
            details={"path": str(destination)},
        )
    _fsync_parent_directory(destination)
    return destination


def _write_private_json(destination: Path, payload: dict[str, Any]) -> Path:
    fd, temporary_path = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        os.replace(temporary_path, destination)
        _fsync_parent_directory(destination)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise
    return destination


@app.command("create")
@handle_errors
def create(
    output_path: str = typer.Argument(..., help="Output path for the hosted transcript JSON"),
    language_code: Optional[str] = typer.Option(None, "--language-code", help="Optional BCP-47 transcript language code"),
    diarize: bool = typer.Option(True, "--diarize/--no-diarize", help="Identify and label different speakers"),
    num_speakers: Optional[int] = typer.Option(None, "--num-speakers", min=1, max=32, help="Expected number of speakers"),
    keyterm: Optional[list[str]] = typer.Option(None, "--keyterm", help="Important term to bias transcription; repeat as needed"),
    no_verbatim: bool = typer.Option(False, "--no-verbatim", help="Allow provider-side removal of verbal disfluencies"),
    resume_job: Optional[str] = typer.Option(None, "--resume-job", help="Resume a pending hosted transcript job without rendering or uploading again"),
    new_job: bool = typer.Option(False, "--new-job", help="Intentionally render and start a separate billed transcript job"),
    force: bool = typer.Option(False, "--force", help="Replace an existing output file"),
):
    """Transcribe the active timeline through the signed-in CutAgent account."""
    set_capability_context("transcript.create", "supported")
    set_execution_engine("api_native")
    enforce_mutation_policy("transcript.create", intended_engine="api_native", mutating=not is_dry_run())
    normalized_language = language_code.strip() if isinstance(language_code, str) and language_code.strip() else None
    normalized_keyterms = []
    seen_keyterms: set[str] = set()
    for value in keyterm or []:
        normalized = str(value).strip()
        if not normalized or normalized in seen_keyterms:
            continue
        seen_keyterms.add(normalized)
        normalized_keyterms.append(normalized)
    if len(normalized_keyterms) > 1000:
        raise ValidationError("At most 1000 --keyterm values are allowed.")
    normalized_resume_job = resume_job.strip() if isinstance(resume_job, str) else None
    if normalized_resume_job and (
        len(normalized_resume_job) > 128
        or not all(character.isalnum() or character in {"_", "-"} for character in normalized_resume_job)
    ):
        raise ValidationError("--resume-job must be a valid hosted transcript job ID.")
    if normalized_resume_job and new_job:
        raise ValidationError("Choose either --resume-job or --new-job, not both.")
    sdk_timeline_guard = os.environ.get("CUTAGENT_SDK_TIMELINE_GUARD", "").strip()
    if sdk_timeline_guard:
        normalized_guard = sdk_timeline_guard
        if not normalized_guard.startswith("sha256:") or len(normalized_guard) != 71:
            raise ValidationError("The private SDK timeline guard is invalid.")
        # This process must prove the exact target before requesting any hosted
        # work. get_connection enforces CUTAGENT_SDK_TIMELINE_GUARD atomically.
        get_connection(require_timeline=True)

    destination = _resolve_output_path(output_path, force=force)
    if is_dry_run():
        if normalized_resume_job:
            dry_run_message(
                f"Would resume hosted transcript job {normalized_resume_job} through the signed-in CutAgent account, then write transcript JSON to {destination}."
            )
        elif new_job:
            dry_run_message(
                f"Would intentionally render and start a separate billed transcript job for the active timeline, then write transcript JSON to {destination}."
            )
        else:
            dry_run_message(
                f"Would render and transcribe the active timeline through the signed-in CutAgent account, then write transcript JSON to {destination}."
            )
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if force:
        _preflight_atomic_replace(destination)
        reservation = None
    else:
        reservation = _reserve_output_path(destination)
    try:
        data = _broker_request({
            "new_job": new_job,
            "resume_job_id": normalized_resume_job,
            **({"target_guard": sdk_timeline_guard} if sdk_timeline_guard else {}),
            "profile": {
                "language_code": normalized_language,
                "diarize": diarize,
                "num_speakers": num_speakers,
                "keyterms": normalized_keyterms,
                "no_verbatim": no_verbatim,
            },
        })
        if data.get("delivery_status") == "acknowledged":
            expected_output_sha256 = str(data.get("output_sha256", "")).lower()
            try:
                actual_output_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
            except OSError as exc:
                raise APICallFailed(
                    "CutAgent confirmed the prior transcript delivery, but its durable output file is unavailable.",
                    details={"path": str(destination)},
                ) from exc
            if not hmac.compare_digest(actual_output_sha256, expected_output_sha256):
                raise APICallFailed(
                    "CutAgent confirmed the prior transcript delivery, but the output file no longer matches it.",
                    details={"path": str(destination)},
                )
            reservation = None
            set_verification_status("verified")
            output({
                "output_path": str(destination),
                "provider": data.get("provider"),
                "model": data.get("model"),
                "timeline": data.get("timeline"),
                "summary": data.get("summary"),
                "usage": data.get("usage"),
                "delivery_recovered": True,
            }, title="Hosted Transcript")
            return
        delivery_id = data.get("delivery_id")
        try:
            normalized_delivery_id = str(uuid.UUID(str(delivery_id), version=4))
        except (ValueError, TypeError, AttributeError) as exc:
            raise APICallFailed("CutAgent returned a transcript result without a durable delivery ID.") from exc
        if normalized_delivery_id != str(delivery_id).lower():
            raise APICallFailed("CutAgent returned an invalid durable transcript delivery ID.")
        delivery_ack = data.get("delivery_ack")
        ack_capability = delivery_ack.get("bridge_capability") if isinstance(delivery_ack, dict) else None
        if not isinstance(ack_capability, str) or not ack_capability.strip():
            raise APICallFailed("CutAgent returned a transcript result without a durable acknowledgement capability.")
        destination = (
            _write_reserved_json(destination, reservation, data["transcript"])
            if reservation is not None
            else _write_private_json(destination, data["transcript"])
        )
        reservation = None
        output_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
        _broker_ack(normalized_delivery_id, ack_capability.strip(), output_sha256)
    except Exception:
        if reservation is not None:
            _cleanup_reservation(destination, reservation)
        raise
    set_verification_status("verified")
    output({
        "output_path": str(destination),
        "provider": data.get("provider"),
        "model": data.get("model"),
        "timeline": data.get("timeline"),
        "summary": data.get("summary"),
        "usage": data.get("usage"),
    }, title="Hosted Transcript")
