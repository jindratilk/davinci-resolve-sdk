"""Length-bounded private JSON-lines host for the signed Rust SDK runtime."""

from __future__ import annotations

import json
import re
import sys
import traceback
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, TextIO

from ._sdk_prepared_action_contract import PREPARED_ACTION_MAX_RESULT_BYTES
from .errors import CLIError
from .prepared_action_composition import (
    build_prepared_action_registry,
    create_prepared_action_authority,
)
from .prepared_action_contributions import (
    build_production_prepared_action_composition,
    build_production_prepared_action_contributions,
    build_production_prepared_action_execution_authorities,
)
from .sdk_prepared_action import PreparedActionDescriptor, PreparedActionError

MAXIMUM_FRAME_BYTES = PREPARED_ACTION_MAX_RESULT_BYTES
_RETIME_PLAYHEAD_PREFIX_MAXIMUM = 1000


def _bounded_private_error_reason(error: Exception) -> str:
    return (
        _private_diagnostic_text(str(error), maximum=500)
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _private_diagnostic_text(value: str, *, maximum: int) -> str:
    sanitized = "".join(
        character if character in "\r\n\t" or " " <= character <= "~" else "?"
        for character in value
    )
    home = str(Path.home())
    if home:
        sanitized = sanitized.replace(home, "<home>")
    sanitized = re.sub(
        r"(?i)\b(bearer|authorization|token)\s*[:=]?\s*[A-Za-z0-9._~+/=-]{8,}",
        r"\1 <redacted>",
        sanitized,
    )
    return sanitized[:maximum]


def _retime_playhead_evidence_prefix(native: Mapping[str, Any]) -> str:
    rows = [
        [
            row.get("target_frame"),
            row.get("final_frame", row.get("actual_frame")),
            row.get("api_result"),
            row.get("restore"),
            row.get("ok"),
        ]
        for row in native.get("moves", [])
    ]
    move_count = native.get("move_count")
    evidence = {
        "failure": native.get("failure"),
        "move_count": move_count,
        "omitted_move_count": max(0, move_count - len(rows)),
        "move_columns": ["target_frame", "observed_frame", "api_result", "restore", "ok"],
        "moves": rows,
    }
    while True:
        prefix = "Retime playhead evidence: " + json.dumps(evidence, separators=(",", ":")) + "\n"
        if len(prefix) <= _RETIME_PLAYHEAD_PREFIX_MAXIMUM:
            return prefix
        evidence["moves"].pop(0)
        evidence["omitted_move_count"] += 1


def _retime_playhead_diagnostic_from_exception(error: BaseException) -> dict | None:
    """Find private evidence through bounded native recovery exception wrappers."""
    seen: set[int] = set()
    current: BaseException | None = error
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        diagnostic = getattr(current, "retime_playhead_diagnostic", None)
        if isinstance(diagnostic, dict):
            return diagnostic
        current = (current.__cause__ if current.__cause__ is not None
                   else None if current.__suppress_context__ else current.__context__)
    return None


class PreparedActionHost:
    def __init__(
        self,
        reader: TextIO,
        writer: TextIO,
        *,
        contributions: Iterable[
            tuple[str, Mapping[str, PreparedActionDescriptor]]
        ],
        execution_authorities: Mapping[str, Any] | None = None,
        diagnostic_writer: TextIO = sys.stderr,
    ):
        self._reader = reader
        self._writer = writer
        self._diagnostic_writer = diagnostic_writer
        self._registry = build_prepared_action_registry(contributions)
        self._runtime_context: dict[str, Any] | None = None
        self._authority = None
        self._callback_sequence = 0
        self._active_request_id: str | None = None
        self._execution_authorities = dict(execution_authorities or {})

    def _write_private_diagnostic(
        self,
        *,
        request_id: str,
        method: str,
        error: Exception,
    ) -> None:
        try:
            message = _private_diagnostic_text(str(error), maximum=500)
            evaluator = (
                self._runtime_context is not None
                and self._runtime_context.get("subscription", {}).get("plan")
                == "sdk_final_evaluator"
            )
            encoded = json.dumps(
                {
                    "kind": "preparedActionHostError",
                    "requestId": request_id,
                    "method": method,
                    "errorClass": error.__class__.__name__[:100],
                    "message": message,
                    **({
                        "trace": _private_diagnostic_text(
                            "".join(traceback.format_exception(error)), maximum=3000,
                        ),
                    } if evaluator else {}),
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )
            self._diagnostic_writer.write(f"{encoded}\n")
            self._diagnostic_writer.flush()
        except Exception:
            # Diagnostics are private best-effort evidence and must never alter
            # the correlated fail-closed response.
            pass

    def _write_private_execution_diagnostic(self, value: Mapping[str, Any]) -> None:
        error = value.get("error")
        if not isinstance(error, BaseException):
            return
        try:
            native = _retime_playhead_diagnostic_from_exception(error)
            prefix = ""
            if isinstance(native, dict):
                prefix = _retime_playhead_evidence_prefix(native)
            encoded = json.dumps(
                {
                    "kind": "preparedActionExecutionError",
                    "requestId": self._active_request_id,
                    "method": "execute",
                    "actionId": str(value.get("actionId") or "")[:200],
                    "operationId": str(value.get("operationId") or "")[:200],
                    "executionId": str(value.get("executionId") or "")[:200],
                    "phase": str(value.get("phase") or "unknown")[:200],
                    "errorClass": error.__class__.__name__[:100],
                    "message": _private_diagnostic_text(str(error), maximum=500),
                    "trace": _private_diagnostic_text(
                        prefix + "".join(traceback.format_exception(error)), maximum=3000,
                    ),
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )
            self._diagnostic_writer.write(f"{encoded}\n")
            self._diagnostic_writer.flush()
        except Exception:
            pass

    def _write(self, value: Mapping[str, Any]) -> None:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > MAXIMUM_FRAME_BYTES:
            raise PreparedActionError("OUTPUT_LIMIT_REACHED", "Private host frame exceeded its limit.")
        self._writer.write(f"{encoded}\n")
        self._writer.flush()

    def _read(self) -> dict[str, Any] | None:
        line = self._reader.readline(MAXIMUM_FRAME_BYTES + 2)
        if not line:
            return None
        if len(line.encode("utf-8")) > MAXIMUM_FRAME_BYTES or not line.endswith("\n"):
            raise PreparedActionError("REQUEST_TOO_LARGE", "Private host frame exceeded its limit.")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise PreparedActionError("INVALID_REQUEST", "Private host frame is invalid.")
        return value

    def _callback(self, parent_request_id: str, method: str, payload: Mapping[str, Any]) -> Any:
        self._callback_sequence += 1
        callback_id = f"callback_{self._callback_sequence}"
        self._write({
            "kind": "callback",
            "parentRequestId": parent_request_id,
            "callbackId": callback_id,
            "sequence": self._callback_sequence,
            "method": method,
            "payload": payload,
        })
        response = self._read()
        correlation = {
            "kind": "callbackResult",
            "parentRequestId": parent_request_id,
            "callbackId": callback_id,
            "sequence": self._callback_sequence,
        }
        if not isinstance(response, dict) or any(
            response.get(key) != value for key, value in correlation.items()
        ):
            raise PreparedActionError("RUNTIME_UNAVAILABLE", "Private host callback failed.")
        callback_error = response.get("error") if response.get("ok") is False else None
        callback_code = callback_error.get("code") if isinstance(callback_error, dict) else None
        allowed_callback_codes = {"RUNTIME_UNAVAILABLE"}
        if method in {"inspectPreparedActionTimeline", "resolveLiveTargets"}:
            allowed_callback_codes.add("STALE_REVISION")
        if method == "resolveLiveTargets":
            allowed_callback_codes.add("CAPABILITY_NEGOTIATION_FAILED")
        if callback_code in allowed_callback_codes \
                and callback_error == {"code": callback_code} \
                and set(response) == {*correlation, "ok", "error"}:
            raise PreparedActionError(callback_code, "Private host callback failed.")
        if response != {
            **correlation,
            "ok": True,
            "value": response.get("value"),
        }:
            raise PreparedActionError("RUNTIME_UNAVAILABLE", "Private host callback failed.")
        return response["value"]

    def _initialize(self, request_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if self._authority is not None:
            raise PreparedActionError("PREPARED_ACTION_INVALID_STATE", "Private host is already initialized.")
        required = {"runtimeContext", "custodyDatabasePath"}
        if set(payload) not in (required, required | {"advertisedActionIds"}) \
                or not isinstance(payload["runtimeContext"], dict):
            raise PreparedActionError("INVALID_REQUEST", "Private host initialization is invalid.")
        advertised = payload.get("advertisedActionIds", self._registry.advertised_action_ids)
        if not isinstance(advertised, (list, tuple)) or not advertised \
                or len(set(advertised)) != len(advertised) \
                or any(not isinstance(action_id, str) or action_id not in self._registry.advertised_action_ids for action_id in advertised):
            raise PreparedActionError("INVALID_REQUEST", "Private host action advertisement is invalid.")
        self._runtime_context = dict(payload["runtimeContext"])

        def redeem(jti: str, claims: Mapping[str, Any], token: str) -> bool:
            if self._active_request_id is None:
                return False
            return self._callback(self._active_request_id, "redeemAuthorization", {
                "jti": jti, "claims": dict(claims), "authorizationToken": token,
            }) is True

        def inspect_timeline(payload: Mapping[str, Any]) -> Any:
            if self._active_request_id is None:
                raise PreparedActionError("RUNTIME_UNAVAILABLE", "Private inspection callback is unavailable.")
            return self._callback(self._active_request_id, "inspectPreparedActionTimeline", dict(payload))

        def resolve_live_targets(payload: Mapping[str, Any]) -> Any:
            if self._active_request_id is None:
                raise PreparedActionError("RUNTIME_UNAVAILABLE", "Private live-target callback is unavailable.")
            return self._callback(self._active_request_id, "resolveLiveTargets", dict(payload))

        if self._runtime_context.get("timeline", {}).get("privateInspectionCallback") is True:
            for execution_authority in self._execution_authorities.values():
                binder = getattr(execution_authority, "bind_private_timeline_inspector", None)
                if callable(binder):
                    binder(inspect_timeline)
        for execution_authority in self._execution_authorities.values():
            binder = getattr(execution_authority, "bind_private_live_target_resolver", None)
            if callable(binder):
                binder(resolve_live_targets)

        self._authority = create_prepared_action_authority(
            registry=self._registry,
            runtime_context=lambda: dict(self._runtime_context or {}),
            redeem_authorization_jti=redeem,
            custody_database_path=payload["custodyDatabasePath"],
            execution_authorities=self._execution_authorities,
            private_failure_observer=(
                self._write_private_execution_diagnostic
                if self._runtime_context.get("subscription", {}).get("plan")
                == "sdk_final_evaluator"
                else None
            ),
        )
        return {
            "advertisedActionIds": sorted(advertised),
            "contractDigest": self._registry.contract_digest,
            "capabilityDigest": self._registry.capability_digest,
            "protocolDigest": self._registry.protocol_digest,
        }

    def dispatch(self, request_id: str, method: str, payload: Mapping[str, Any]) -> Any:
        if method == "initialize":
            return self._initialize(request_id, payload)
        if self._authority is None:
            raise PreparedActionError("PREPARED_ACTION_INVALID_STATE", "Private host is not initialized.")
        if method == "prepare":
            if set(payload) not in ({"request"}, {"request", "mutationBase"}):
                raise PreparedActionError("INVALID_REQUEST", "Private prepare envelope is invalid.")
            return self._authority.prepare(payload["request"], payload.get("mutationBase"))
        if method == "admit":
            self._authority.admit(payload["receipt"], payload.get("authorizationToken"))
            return None
        if method == "execute":
            return self._authority.execute(payload["receipt"])
        if method == "recoverTerminal":
            return self._authority.recover_terminal(payload)
        if method == "revoke":
            self._authority.revoke(payload["receipt"])
            return None
        raise PreparedActionError("INVALID_REQUEST", "Private host method is invalid.")

    def run(self) -> None:
        while request := self._read():
            request_id = request.get("requestId")
            method = request.get("method")
            payload = request.get("payload")
            if not isinstance(request_id, str) or not isinstance(method, str) or not isinstance(payload, dict):
                raise PreparedActionError("INVALID_REQUEST", "Private host request is invalid.")
            try:
                self._active_request_id = request_id
                value = self.dispatch(request_id, method, payload)
                self._write({"kind": "response", "requestId": request_id, "ok": True, "value": value})
            except PreparedActionError as error:
                self._write({"kind": "response", "requestId": request_id, "ok": False, "error": {"code": error.code, "message": str(error)}})
            except Exception as error:
                self._write_private_diagnostic(
                    request_id=request_id,
                    method=method,
                    error=error,
                )
                if isinstance(error, CLIError):
                    code = error.code
                    message = error.__class__.message
                    private_diagnostic = (
                        {
                            "hostPhase": method[:100],
                            "reason": _bounded_private_error_reason(error),
                        }
                        if code == "VALIDATION_ERROR"
                        else None
                    )
                else:
                    code = "RUNTIME_UNAVAILABLE"
                    message = "Private host request failed."
                    private_diagnostic = None
                self._write({
                    "kind": "response",
                    "requestId": request_id,
                    "ok": False,
                    "error": {
                        "code": code,
                        "message": message,
                        **(
                            {"privateDiagnostic": private_diagnostic}
                            if private_diagnostic is not None
                            else {}
                        ),
                    },
                })
            finally:
                self._active_request_id = None


def run_prepared_action_host(
    reader: TextIO = sys.stdin,
    writer: TextIO = sys.stdout,
    *,
    contributions: Iterable[tuple[str, Mapping[str, PreparedActionDescriptor]]] | None = None,
    execution_authorities: Mapping[str, Any] | None = None,
) -> None:
    if contributions is None and execution_authorities is None:
        contributions, execution_authorities = (
            build_production_prepared_action_composition()
        )
    PreparedActionHost(
        reader,
        writer,
        contributions=(contributions if contributions is not None else build_production_prepared_action_contributions()),
        execution_authorities=(
            execution_authorities
            if execution_authorities is not None
            else build_production_prepared_action_execution_authorities()
        ),
    ).run()


def main() -> None:
    run_prepared_action_host()


if __name__ == "__main__":
    main()
