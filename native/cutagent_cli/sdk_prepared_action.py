"""Private signed-runtime authority for typed SDK prepare/admit/execute actions.

This is not a public CutAgent CLI command surface. Domain descriptor packets
register private lowering, live target resolution, verification, and recovery.
An action with any missing stage cannot prepare and must remain unadvertised.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import secrets
import sqlite3
import struct
import threading
import time
from types import MappingProxyType
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from ._sdk_prepared_action_contract import (
    PREPARED_ACTION_MAX_PREPARE_BYTES,
    PREPARED_ACTION_MAX_IMPACT_BYTES,
    PREPARED_ACTION_MAX_OUTSTANDING_RECEIPTS,
    PREPARED_ACTION_MAX_RECEIPT_BYTES,
    PREPARED_ACTION_MAX_RESULT_BYTES,
    PREPARED_ACTION_PROTOCOL_VERSION,
    PREPARED_ACTION_KERNEL_DIGEST,
    PREPARED_ACTION_CONTRACT_DIGEST,
    PREPARED_ACTION_CAPABILITY_DIGEST,
    PREPARED_ACTION_ACTION_METADATA,
    PREPARED_ACTION_PUBLIC_RESULT_MAX_BYTES,
    PREPARED_ACTION_RECEIPT_TTL_MS,
)
from .authz import _verify_signature
from .errors import AuthorizationError

_DIGEST_PREFIX = b"cutagent-sdk-prepared-action-v1\0"
_DIGEST_LABELS = {
    "account",
    "subscription",
    "session",
    "action",
    "input",
    "contract",
    "capability",
    "protocol",
    "app-artifact",
    "runtime-artifact",
    "cli-artifact",
    "packaged-ancestry",
    "project",
    "timeline",
    "private-bindings",
    "targets",
    "pre-state",
    "impact",
    "receipt",
    "execution",
    "idempotency",
}
_AUTH_ISSUER = "cutagent-cloud"
_AUTH_AUDIENCE = "cutagent-cli"
_AUTH_TOKEN_TYPE = "cutagent_sdk_prepared_action"
_AUTH_CAPABILITY = "cutagent-sdk.prepared-action"
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return value


class PreparedActionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _normalized(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 9_007_199_254_740_991:
            raise PreparedActionError(
                "PREPARED_ACTION_INVALID",
                "Prepared action integer exceeded the canonical range.",
            )
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PreparedActionError(
                "PREPARED_ACTION_INVALID", "Prepared action number must be finite."
            )
        if value == 0:
            return 0
        if value.is_integer() and abs(value) <= 9_007_199_254_740_991:
            return int(value)
        return {"$cutagentFloat64": struct.pack(">d", value).hex()}
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _normalized(value[key]) for key in sorted(value)}
    raise PreparedActionError(
        "PREPARED_ACTION_INVALID", "Prepared action data must be canonical JSON."
    )


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _normalized(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _freeze_json(value: Any) -> Any:
    # Canonical bytes are hash material, not a transport: fractional numbers
    # become tagged objects there. Validate without changing runtime values.
    canonical_bytes(value)
    return _deep_freeze(value)


def prepared_action_digest(label: str, value: Any) -> str:
    if label not in _DIGEST_LABELS:
        raise PreparedActionError(
            "PREPARED_ACTION_INVALID", "Prepared action digest label is unknown."
        )
    material = _DIGEST_PREFIX + label.encode() + bytes((0,)) + canonical_bytes(value)
    return f"sha256:{hashlib.sha256(material).hexdigest()}"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(f"{value}{'=' * (-len(value) % 4)}".encode("ascii"))


def _iso(milliseconds: int) -> str:
    return (
        datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


class PreparedActionDescriptor(Protocol):
    operation_class: str
    version: int
    capability_id: str | None

    def validate_input(self, value: Any) -> Any: ...
    def prepare(self, context: Mapping[str, Any], value: Any) -> Mapping[str, Any]: ...
    def resolve_current(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...
    def execute(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any]
    ) -> Any: ...
    def verify(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any
    ) -> Mapping[str, Any]: ...
    def recover(
        self,
        context: Mapping[str, Any],
        prepared: Mapping[str, Any],
        failure: BaseException,
    ) -> Mapping[str, Any]: ...
    def project_result(
        self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any
    ) -> Any: ...
    def validate_public_result(self, value: Any) -> bool: ...


@dataclass(frozen=True)
class _FrozenPreparedActionDescriptor:
    operation_class: str
    version: int
    capability_id: str | None
    validate_input: Callable[[Any], Any]
    prepare: Callable[[Mapping[str, Any], Any], Mapping[str, Any]]
    resolve_current: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]
    execute: Callable[[Mapping[str, Any], Mapping[str, Any]], Any]
    verify: Callable[[Mapping[str, Any], Mapping[str, Any], Any], Mapping[str, Any]]
    recover: Callable[
        [Mapping[str, Any], Mapping[str, Any], BaseException], Mapping[str, Any]
    ]
    project_result: Callable[[Mapping[str, Any], Mapping[str, Any], Any], Any]
    validate_public_result: Callable[[Any], bool]


@dataclass(frozen=True)
class FrozenPreparedActionRegistry:
    descriptors: Mapping[str, _FrozenPreparedActionDescriptor]
    metadata: Mapping[str, tuple[str, int, str | None]]
    unavailable_action_ids: tuple[str, ...]
    contract_digest: str
    capability_digest: str
    protocol_digest: str

    @property
    def advertised_action_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.descriptors))


class PreparedActionRegistry:
    """Sole composition seam for private domain descriptor contributions."""

    _STAGES = (
        "validate_input",
        "prepare",
        "resolve_current",
        "execute",
        "verify",
        "recover",
        "project_result",
        "validate_public_result",
    )

    def __init__(self):
        self._descriptors: dict[str, PreparedActionDescriptor] = {}
        self._unavailable: set[str] = set()
        self._frozen = False

    def register_contribution(
        self,
        contribution_name: str,
        descriptors: Mapping[str, PreparedActionDescriptor],
    ) -> None:
        if (
            self._frozen
            or not isinstance(contribution_name, str)
            or not contribution_name
        ):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE",
                "Prepared-action registry is already frozen or unnamed.",
            )
        for action_id, descriptor in descriptors.items():
            if action_id in self._descriptors or action_id in self._unavailable:
                raise PreparedActionError(
                    "RUNTIME_INCOMPATIBLE",
                    f"Duplicate prepared action registration: {action_id}",
                )
            complete = (
                isinstance(action_id, str)
                and (authoritative := PREPARED_ACTION_ACTION_METADATA.get(action_id))
                is not None
                and getattr(descriptor, "operation_class", None)
                == authoritative["operationClass"]
                and getattr(descriptor, "version", None) == authoritative["version"]
                and getattr(descriptor, "capability_id", None)
                == authoritative["capabilityId"]
                and all(
                    callable(getattr(descriptor, stage, None)) for stage in self._STAGES
                )
            )
            if complete:
                self._descriptors[action_id] = descriptor
            else:
                self._unavailable.add(str(action_id))

    def freeze(
        self,
    ) -> FrozenPreparedActionRegistry:
        self._frozen = True
        frozen_descriptors = {
            action_id: _FrozenPreparedActionDescriptor(
                operation_class=descriptor.operation_class,
                version=descriptor.version,
                capability_id=descriptor.capability_id,
                **{stage: getattr(descriptor, stage) for stage in self._STAGES},
            )
            for action_id, descriptor in self._descriptors.items()
        }
        return FrozenPreparedActionRegistry(
            descriptors=MappingProxyType(frozen_descriptors),
            metadata=MappingProxyType(
                {
                    action_id: (
                        descriptor.operation_class,
                        descriptor.version,
                        descriptor.capability_id,
                    )
                    for action_id, descriptor in frozen_descriptors.items()
                }
            ),
            unavailable_action_ids=tuple(sorted(self._unavailable)),
            contract_digest=PREPARED_ACTION_CONTRACT_DIGEST,
            capability_digest=PREPARED_ACTION_CAPABILITY_DIGEST,
            protocol_digest=PREPARED_ACTION_KERNEL_DIGEST,
        )


class FilePreparedActionIdempotencyCustody:
    """Permanent compact tombstones with explicit fail-closed storage ceilings."""

    MAXIMUM_RECORDS = 100_000
    MAXIMUM_DATABASE_BYTES = 64 * 1024 * 1024

    def __init__(
        self,
        database_path: str | Path,
        *,
        maximum_records: int = MAXIMUM_RECORDS,
        maximum_database_bytes: int = MAXIMUM_DATABASE_BYTES,
    ):
        self._path = Path(database_path)
        self._maximum_records = maximum_records
        self._maximum_database_bytes = maximum_database_bytes
        if (
            not 1 <= maximum_records <= self.MAXIMUM_RECORDS
            or not 16 * 1024 <= maximum_database_bytes <= self.MAXIMUM_DATABASE_BYTES
        ):
            raise ValueError("Prepared-action custody limits are invalid.")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "create table if not exists prepared_action_custody ("
                "custody_key text primary key, binding_digest text not null, terminal_digest text, terminal_json text, claimed_at text not null)"
            )
            columns = {str(row[1]) for row in connection.execute("pragma table_info(prepared_action_custody)")}
            if "terminal_json" not in columns:
                connection.execute("alter table prepared_action_custody add column terminal_json text")
        try:
            self._path.chmod(0o600)
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5, isolation_level=None)
        try:
            connection.execute("pragma journal_mode = DELETE")
            connection.execute("pragma synchronous = FULL")
            page_size = int(connection.execute("pragma page_size").fetchone()[0])
            maximum_pages = self._maximum_database_bytes // page_size
            applied = int(
                connection.execute(
                    f"pragma max_page_count = {maximum_pages}"
                ).fetchone()[0]
            )
            current = int(connection.execute("pragma page_count").fetchone()[0])
            if applied > maximum_pages or current > maximum_pages:
                raise PreparedActionError(
                    "RESOURCE_EXHAUSTED",
                    "Prepared-action durable custody exceeds its configured limit.",
                )
            return connection
        except Exception:
            connection.close()
            raise

    @staticmethod
    def _storage_error(exc: sqlite3.Error) -> PreparedActionError | None:
        if (
            getattr(exc, "sqlite_errorcode", None) == getattr(sqlite3, "SQLITE_FULL", 13)
            or "database or disk is full" in str(exc).lower()
        ):
            return PreparedActionError(
                "RESOURCE_EXHAUSTED",
                "Prepared-action durable custody reached its configured byte limit.",
            )
        return None

    def claim(self, custody_key: str, binding: Mapping[str, Any]) -> bool:
        binding_digest = prepared_action_digest("idempotency", binding)
        with self._connect() as connection:
            connection.execute("begin immediate")
            existing = connection.execute(
                "select binding_digest from prepared_action_custody where custody_key = ?",
                (custody_key,),
            ).fetchone()
            if existing is not None:
                connection.rollback()
                return False
            count = int(
                connection.execute(
                    "select count(*) from prepared_action_custody"
                ).fetchone()[0]
            )
            if count >= self._maximum_records:
                connection.rollback()
                raise PreparedActionError(
                    "RESOURCE_EXHAUSTED",
                    "Prepared-action durable custody reached its configured limit.",
                )
            try:
                connection.execute(
                    "insert into prepared_action_custody (custody_key, binding_digest, claimed_at) values (?, ?, ?)",
                    (custody_key, binding_digest, _iso(int(time.time() * 1000))),
                )
            except sqlite3.Error as exc:
                connection.rollback()
                if translated := self._storage_error(exc):
                    raise translated from exc
                raise
            connection.commit()
            return True

    def record_terminal(self, custody_key: str, terminal: Mapping[str, Any]) -> None:
        terminal_digest = prepared_action_digest("idempotency", terminal)
        # Persist the JSON value itself; the canonical digest representation
        # replaces fractional numbers with objects and cannot round-trip it.
        terminal_json = json.dumps(
            terminal, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
        if len(terminal_json.encode("utf-8")) > PREPARED_ACTION_MAX_RESULT_BYTES:
            raise PreparedActionError("OUTPUT_LIMIT_REACHED", "Prepared-action terminal custody exceeded its bound.")
        with self._connect() as connection:
            connection.execute("begin immediate")
            try:
                updated = connection.execute(
                    "update prepared_action_custody set terminal_digest = ?, terminal_json = ? where custody_key = ? and terminal_digest is null",
                    (terminal_digest, terminal_json, custody_key),
                ).rowcount
            except sqlite3.Error as exc:
                connection.rollback()
                if translated := self._storage_error(exc):
                    raise translated from exc
                raise
            if updated != 1:
                connection.rollback()
                raise PreparedActionError(
                    "IDEMPOTENCY_CONFLICT",
                    "Prepared-action terminal custody is unavailable or already final.",
                )
            connection.commit()

    def terminal_digest(self, custody_key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "select terminal_digest from prepared_action_custody where custody_key = ?",
                (custody_key,),
            ).fetchone()
        return str(row[0]) if row and row[0] else None

    def terminal(self, custody_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "select terminal_digest, terminal_json from prepared_action_custody where custody_key = ?",
                (custody_key,),
            ).fetchone()
        if not row or not row[0] or not row[1]:
            return None
        terminal = json.loads(str(row[1]))
        if prepared_action_digest("idempotency", terminal) != str(row[0]):
            raise PreparedActionError("RUNTIME_INCOMPATIBLE", "Prepared-action terminal custody digest drifted.")
        return terminal


@dataclass
class _Record:
    receipt: str
    claims: dict[str, Any]
    descriptor: _FrozenPreparedActionDescriptor
    context: dict[str, Any]
    prepared: dict[str, Any]
    state: str = "prepared"
    authorization_jti: str | None = None
    custody_key: str | None = None


class PreparedActionAuthority:
    """One process-local receipt store owned by a signed runtime instance."""

    def __init__(
        self,
        *,
        registry: FrozenPreparedActionRegistry,
        runtime_context: Callable[[], Mapping[str, Any]],
        redeem_authorization_jti: Callable[[str, Mapping[str, Any], str], bool],
        claim_idempotency: Callable[[str, Mapping[str, Any]], bool],
        record_idempotency_terminal: Callable[[str, Mapping[str, Any]], None],
        load_idempotency_terminal: Callable[[str], Mapping[str, Any] | None],
        execution_authorities: Mapping[str, Any] | None = None,
        private_failure_observer: Callable[[Mapping[str, Any]], None] | None = None,
        now_ms: Callable[[], int] | None = None,
    ):
        if (
            not isinstance(registry, FrozenPreparedActionRegistry)
            or registry.protocol_digest != PREPARED_ACTION_KERNEL_DIGEST
        ):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE", "Prepared-action registry is not authoritative."
            )
        self._registry = registry
        self._descriptors = dict(registry.descriptors)
        self._runtime_context = runtime_context
        self._redeem_authorization_jti = redeem_authorization_jti
        self._claim_idempotency = claim_idempotency
        self._record_idempotency_terminal = record_idempotency_terminal
        self._load_idempotency_terminal = load_idempotency_terminal
        self._execution_authorities = dict(execution_authorities or {})
        if private_failure_observer is not None and not callable(private_failure_observer):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE",
                "Prepared-action private failure observer is invalid.",
            )
        self._private_failure_observer = private_failure_observer
        if any(
            action_id not in self._descriptors
            or not callable(getattr(authority, "invoke_admitted_handler", None))
            for action_id, authority in self._execution_authorities.items()
        ):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE",
                "Prepared-action execution authority composition is invalid.",
            )
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._key = secrets.token_bytes(32)
        self._records: dict[str, _Record] = {}
        self._active_executions: dict[
            object, tuple[str, object, Mapping[str, Any]]
        ] = {}
        self._active_execution_lock = threading.RLock()
        self._lock = threading.RLock()

    def _authorizes_prepared_action_execution(
        self,
        execution_token: object,
        action_id: str,
        authority: object,
        exact_request_binding: Mapping[str, Any],
    ) -> bool:
        if execution_token is None or not isinstance(exact_request_binding, Mapping):
            return False
        with self._active_execution_lock:
            active = self._active_executions.get(execution_token)
        return bool(
            active is not None
            and active[0] == action_id
            and active[1] is authority
            and active[2] is exact_request_binding
        )

    def _seal(self, claims: Mapping[str, Any]) -> str:
        payload = _b64(canonical_bytes(claims))
        signature = _b64(
            hmac.new(self._key, payload.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{payload}.{signature}"

    def _open(self, receipt: str) -> _Record:
        if (
            not isinstance(receipt, str)
            or len(receipt.encode()) > PREPARED_ACTION_MAX_RECEIPT_BYTES
        ):
            raise PreparedActionError(
                "PREPARED_ACTION_INVALID", "Prepared action receipt is invalid."
            )
        parts = receipt.split(".")
        if len(parts) != 2:
            raise PreparedActionError(
                "PREPARED_ACTION_INVALID", "Prepared action receipt is invalid."
            )
        payload, signature = parts
        expected = _b64(
            hmac.new(self._key, payload.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise PreparedActionError(
                "PREPARED_ACTION_INVALID", "Prepared action receipt is invalid."
            )
        try:
            claims = json.loads(_unb64(payload))
        except Exception as exc:
            raise PreparedActionError(
                "PREPARED_ACTION_INVALID", "Prepared action receipt is invalid."
            ) from exc
        record = self._records.get(str(claims.get("receiptId", "")))
        if record is None or not hmac.compare_digest(
            canonical_bytes(record.claims), canonical_bytes(claims)
        ):
            raise PreparedActionError(
                "PREPARED_ACTION_INVALID", "Prepared action receipt is unavailable."
            )
        return record

    def prepare(
        self,
        request: Mapping[str, Any],
        mutation_base: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if len(canonical_bytes(request)) > PREPARED_ACTION_MAX_PREPARE_BYTES:
            raise PreparedActionError(
                "REQUEST_TOO_LARGE", "Prepared action request exceeded its limit."
            )
        allowed = {
            "protocolVersion",
            "actionId",
            "actionContractVersion",
            "input",
            "contractDigest",
            "capabilityDigest",
            "identities",
            "revisions",
            "idempotencyKey",
            "requestId",
            "operationId",
            "executionId",
        }
        if (
            set(request) != allowed
            or request.get("protocolVersion") != PREPARED_ACTION_PROTOCOL_VERSION
        ):
            raise PreparedActionError(
                "PREPARED_ACTION_INVALID", "Prepared action request shape is invalid."
            )
        action_id = request.get("actionId")
        descriptor = (
            self._descriptors.get(action_id) if isinstance(action_id, str) else None
        )
        if descriptor is None:
            raise PreparedActionError(
                "CAPABILITY_UNAVAILABLE",
                "The typed action has no complete private descriptor.",
            )
        if (
            request["contractDigest"] != self._registry.contract_digest
            or request["capabilityDigest"] != self._registry.capability_digest
        ):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE",
                "Prepared-action contract or capability digest drifted.",
            )
        registered_class, registered_version, registered_capability = (
            self._registry.metadata[action_id]
        )
        if (
            descriptor.operation_class != registered_class
            or descriptor.version != registered_version
            or descriptor.capability_id != registered_capability
            or descriptor.version != request.get("actionContractVersion")
        ):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE", "The typed action descriptor is incompatible."
            )
        value = descriptor.validate_input(request.get("input"))
        context = dict(self._runtime_context())
        session_binding = context.get("session", {})
        if any(
            session_binding.get(key) != expected
            for key, expected in {
                "preparedActionKernelDigest": PREPARED_ACTION_KERNEL_DIGEST,
                "preparedActionContractDigest": PREPARED_ACTION_CONTRACT_DIGEST,
                "preparedActionCapabilityDigest": PREPARED_ACTION_CAPABILITY_DIGEST,
            }.items()
        ):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE",
                "The trusted runtime session does not bind the prepared-action authority.",
            )
        execution = {
            key: request[key]
            for key in ("requestId", "operationId", "executionId", "idempotencyKey")
        }
        mutation_base_required_keys = {
            "contractVersion", "carrier", "minimumBinding", "registryDigest",
            "canonicalRequestDigest", "referencedPayloadDigests", "requestId",
            "operationId", "executionId",
            "projectLibraryId",
        }
        mutation_base_keys = mutation_base_required_keys | {
            "projectId", "timelineId", "projectRevision", "timelineRevision",
        }
        if descriptor.operation_class == "mutation":
            if (
                not isinstance(mutation_base, Mapping)
                or not mutation_base_required_keys.issubset(mutation_base)
                or not set(mutation_base).issubset(mutation_base_keys)
            ):
                raise PreparedActionError("INVALID_REQUEST", "Prepared mutation base is invalid.")
            if any(mutation_base.get(key) != request.get(key) for key in ("requestId", "operationId", "executionId")):
                raise PreparedActionError("INVALID_REQUEST", "Prepared mutation correlation drifted.")
            exact_mutation_base = _freeze_json(mutation_base)
        elif mutation_base is not None:
            raise PreparedActionError("INVALID_REQUEST", "Prepared reads cannot carry a mutation base.")
        else:
            exact_mutation_base = None
        context.update(
            {
                "actionId": action_id,
                "operationId": request["operationId"],
                "executionId": request["executionId"],
                "execution": execution,
                # Exact accepted public binding for domain services. It is an
                # immutable in-process value, never a caller-supplied service
                # or callable inside the JSON runtime context.
                "exactRequestBinding": _freeze_json(request),
                **({"mutationBase": exact_mutation_base} if exact_mutation_base is not None else {}),
            }
        )
        context["privateBindings"] = _freeze_json(context.get("privateBindings", {}))
        if authority := self._execution_authorities.get(action_id):
            context["executionAuthority"] = authority
        private = _deep_thaw(dict(descriptor.prepare(context, value)))
        required_private = {
            "targets",
            "preState",
            "impact",
            "lowering",
            "verification",
            "recovery",
        }
        if (
            not required_private.issubset(private)
            or private["impact"].get("complete") is not True
        ):
            raise PreparedActionError(
                "CAPABILITY_UNAVAILABLE", "The typed action descriptor is incomplete."
            )
        if descriptor.operation_class == "mutation":
            impact_base = {key: private["impact"][key] for key in mutation_base}
            if canonical_bytes(impact_base) != canonical_bytes(mutation_base):
                raise PreparedActionError(
                    "CAPABILITY_UNAVAILABLE",
                    "Mutation descriptor changed the carrier-owned mutation base.",
                )
            verification_policy = private["impact"].get("verificationPolicy")
            if (
                not isinstance(verification_policy, Mapping)
                or set(verification_policy)
                != {
                    "minimumEvidence",
                    "requireProtectedStatePreserved",
                    "protectedTargetEvidence",
                }
                or not isinstance(verification_policy.get("minimumEvidence"), list)
                or not verification_policy["minimumEvidence"]
            ):
                raise PreparedActionError(
                    "CAPABILITY_UNAVAILABLE",
                    "Mutation descriptor omitted its protected-state verification policy.",
                )
        if len(canonical_bytes(private["impact"])) > PREPARED_ACTION_MAX_IMPACT_BYTES:
            raise PreparedActionError(
                "REQUEST_TOO_LARGE", "Prepared action impact exceeded its limit."
            )
        self._assert_request_context(request, context, private)
        receipt_id = f"prepared_{secrets.token_urlsafe(24)}"
        artifact = context["artifacts"]
        if (
            artifact.get("protocol", {}).get("preparedActionKernelDigest")
            != self._registry.protocol_digest
        ):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE",
                "Signed runtime prepared-action protocol drifted.",
            )
        claims = {
            "receiptId": receipt_id,
            "accountDigest": prepared_action_digest("account", context["localPrincipal"]),
            "subscriptionDigest": prepared_action_digest(
                "subscription", None
            ),
            "sessionDigest": prepared_action_digest("session", context["session"]),
            "actionDigest": prepared_action_digest(
                "action",
                {"actionId": action_id, "actionContractVersion": descriptor.version},
            ),
            "inputDigest": prepared_action_digest(
                "input",
                {
                    "actionId": action_id,
                    "actionContractVersion": descriptor.version,
                    "normalizedInput": value,
                },
            ),
            "contractDigest": request["contractDigest"],
            "capabilityDigest": request["capabilityDigest"],
            "protocolDigest": prepared_action_digest("protocol", artifact["protocol"]),
            "appArtifactDigest": prepared_action_digest(
                "app-artifact", artifact["app"]
            ),
            "runtimeArtifactDigest": prepared_action_digest(
                "runtime-artifact", artifact["runtime"]
            ),
            "cliArtifactDigest": prepared_action_digest(
                "cli-artifact", artifact["cli"]
            ),
            "projectDigest": prepared_action_digest("project", context["project"]),
            "timelineDigest": prepared_action_digest("timeline", context["timeline"]),
            "privateBindingsDigest": prepared_action_digest(
                "private-bindings", _deep_thaw(context.get("privateBindings", {}))
            ),
            "targetsDigest": prepared_action_digest(
                "targets", {"orderedStableTargets": private["targets"]}
            ),
            "preStateDigest": prepared_action_digest(
                "pre-state",
                {
                    "descriptorVersion": descriptor.version,
                    "privateCanonicalSnapshot": private["preState"],
                },
            ),
            "impactDigest": prepared_action_digest(
                "impact",
                {
                    "contractVersion": PREPARED_ACTION_PROTOCOL_VERSION,
                    "sanitizedCompleteImpact": private["impact"],
                },
            ),
            "expiresAt": self._now_ms() + PREPARED_ACTION_RECEIPT_TTL_MS,
            "executionDigest": prepared_action_digest("execution", execution),
        }
        claims["packagedAncestryDigest"] = prepared_action_digest(
            "packaged-ancestry",
            {
                "appArtifactDigest": claims["appArtifactDigest"],
                "runtimeArtifactDigest": claims["runtimeArtifactDigest"],
                "cliArtifactDigest": claims["cliArtifactDigest"],
                "protocolDigest": claims["protocolDigest"],
                "runtimeManifestDigest": artifact["runtimeManifestDigest"],
            },
        )
        custody_key = prepared_action_digest(
            "idempotency",
            {
                "accountDigest": claims["accountDigest"],
                "idempotencyKey": request["idempotencyKey"],
            },
        )
        custody_binding = {
            "actionDigest": claims["actionDigest"],
            "inputDigest": claims["inputDigest"],
            "executionDigest": claims["executionDigest"],
            "operationId": request["operationId"],
            "executionId": request["executionId"],
        }
        receipt = self._seal(claims)
        with self._lock:
            self._prune_expired()
            if len(self._records) >= PREPARED_ACTION_MAX_OUTSTANDING_RECEIPTS:
                raise PreparedActionError(
                    "RESOURCE_EXHAUSTED",
                    "The signed runtime has too many outstanding prepared actions.",
                )
            if not self._claim_idempotency(custody_key, custody_binding):
                raise PreparedActionError(
                    "IDEMPOTENCY_CONFLICT",
                    "This idempotency key already has durable execution custody.",
                )
            self._records[receipt_id] = _Record(
                receipt, claims, descriptor, context, private, custody_key=custody_key
            )
        record = self._records[receipt_id]
        return {
            "protocolVersion": PREPARED_ACTION_PROTOCOL_VERSION,
            "receipt": receipt,
            "receiptDigest": prepared_action_digest("receipt", receipt),
            "expiresAt": _iso(claims["expiresAt"]),
            "operationClass": descriptor.operation_class,
            "impact": private["impact"],
            "authorizationBinding": self._authorization_claims(record),
        }

    def admit(
        self,
        receipt: str,
        authorization_token: str,
    ) -> None:
        with self._lock:
            record = self._open(receipt)
            if record.claims["expiresAt"] <= self._now_ms():
                raise PreparedActionError(
                    "PREPARED_ACTION_EXPIRED", "Prepared action receipt expired."
                )
            if record.state != "prepared":
                raise PreparedActionError(
                    "PREPARED_ACTION_INVALID_STATE",
                    "Prepared action admission state is invalid.",
                )
            claims = self._verify_authorization(authorization_token)
            expected = {
                **self._authorization_claims(record),
                "actionId": record.context["actionId"],
                "operationClass": record.descriptor.operation_class,
            }
            account_subject = record.context.get("account", {}).get("accountSubject")
            if (
                not isinstance(account_subject, str)
                or claims.get("sub") != account_subject
                or any(claims.get(key) != value for key, value in expected.items())
            ):
                raise PreparedActionError(
                    "PREPARED_ACTION_BINDING_MISMATCH",
                    "Authorization does not match the prepared action.",
                )
            if not self._redeem_authorization_jti(
                str(claims["jti"]), claims, authorization_token
            ):
                raise PreparedActionError(
                    "AUTH_TOKEN_INVALID",
                    "Prepared action authorization was already redeemed.",
                )
            record.authorization_jti = str(claims["jti"])
            record.state = "authorized"

    def _pre_mutation_failure_terminal(
        self, record: _Record, failure: PreparedActionError
    ) -> dict[str, Any]:
        """Seal authenticated signed-host stale truth before descriptor mutation."""
        failure.possible_mutation = "none"
        failure.usage = "released"
        self._observe_private_failure(record, failure, "descriptor.resolve_current")
        terminal = self._bounded_terminal(
            record,
            self._failed_terminal(
                record,
                failure,
                recovery={
                    "outcome": "not_needed",
                    "attempted": False,
                    "manualActionRequired": False,
                },
            ),
        )
        self._assert_terminal_schema(record, terminal)
        record.state = "failed"
        if record.custody_key:
            try:
                self._record_idempotency_terminal(record.custody_key, terminal)
            except Exception:
                terminal = {
                    **terminal,
                    "custody": "terminal_persistence_unavailable",
                    "retrySafe": False,
                }
        return terminal

    def execute(self, receipt: str) -> dict[str, Any]:
        with self._lock:
            record = self._open(receipt)
            if record.claims["expiresAt"] <= self._now_ms():
                raise PreparedActionError(
                    "PREPARED_ACTION_EXPIRED", "Prepared action receipt expired."
                )
            if record.state != "authorized":
                raise PreparedActionError(
                    "PREPARED_ACTION_REPLAYED",
                    "Prepared action receipt was already consumed.",
                )
            try:
                current_context = dict(self._runtime_context())
                self._assert_current_context(record, current_context)
                for key in (
                    "actionId", "operationId", "executionId", "execution",
                    "exactRequestBinding", "mutationBase", "privateBindings",
                ):
                    if key in record.context:
                        current_context[key] = record.context[key]
                execution_authority = self._execution_authorities.get(
                    record.context["actionId"]
                )
                exact_request_binding = current_context.get("exactRequestBinding")
                if execution_authority is not None:
                    current_context["executionAuthority"] = execution_authority
                current = dict(
                    record.descriptor.resolve_current(current_context, record.prepared)
                )
                if execution_authority is not None and (
                    current_context.get("executionAuthority") is not execution_authority
                    or current_context.get("exactRequestBinding")
                    is not exact_request_binding
                ):
                    raise PreparedActionError(
                        "PREPARED_ACTION_INVALID_STATE",
                        "Prepared action authority or exact binding changed during resolution.",
                    )
            except Exception as failure:
                record.state = "revoked"
                if (
                    isinstance(failure, PreparedActionError)
                    and failure.code == "STALE_REVISION"
                ):
                    return self._pre_mutation_failure_terminal(record, failure)
                raise
            if (
                prepared_action_digest(
                    "targets", {"orderedStableTargets": current.get("targets")}
                )
                != record.claims["targetsDigest"]
                or prepared_action_digest(
                    "pre-state",
                    {
                        "descriptorVersion": record.descriptor.version,
                        "privateCanonicalSnapshot": current.get("preState"),
                    },
                )
                != record.claims["preStateDigest"]
            ):
                record.state = "revoked"
                failure = PreparedActionError(
                    "STALE_REVISION",
                    "Prepared action target or pre-state changed before execution.",
                )
                return self._pre_mutation_failure_terminal(record, failure)
            record.state = (
                "executing"  # mutex-protected consume before possible mutation
            )
        failure_phase = "descriptor.execute"
        verification = None
        try:
            if execution_authority is None:
                private_result = record.descriptor.execute(current_context, record.prepared)
            else:
                execution_token = object()
                binding = exact_request_binding
                with self._active_execution_lock:
                    self._active_executions[execution_token] = (
                        record.context["actionId"],
                        execution_authority,
                        binding,
                    )
                current_context["_preparedActionCarrier"] = self
                current_context["_preparedActionExecutionToken"] = execution_token
                try:
                    private_result = record.descriptor.execute(current_context, record.prepared)
                finally:
                    current_context.pop("_preparedActionCarrier", None)
                    current_context.pop("_preparedActionExecutionToken", None)
                    with self._active_execution_lock:
                        self._active_executions.pop(execution_token, None)
            failure_phase = "descriptor.verify"
            verification = self._validated_verification(
                record,
                record.descriptor.verify(
                    current_context, record.prepared, private_result
                ),
            )
            if verification["outcome"] != "passed":
                raise PreparedActionError(
                    "VERIFICATION_FAILED", "Prepared action verification failed."
                )
            failure_phase = "descriptor.project_result"
            result = record.descriptor.project_result(
                current_context, record.prepared, private_result
            )
            if record.descriptor.validate_public_result(result) is not True:
                raise PreparedActionError(
                    "RUNTIME_INCOMPATIBLE",
                    "The action result does not match its exact public schema.",
                )
            self._assert_public_projection(result)
            semantic_no_change = (
                record.descriptor.operation_class == "mutation"
                and isinstance(result, dict)
                and result.get("outcome") == "no_change"
            )
            terminal = {
                "status": "succeeded",
                "operationId": record.context["operationId"],
                "executionId": record.context["executionId"],
                "actionId": record.context["actionId"],
                "possibleMutation": "none"
                if record.descriptor.operation_class == "read" or semantic_no_change
                else "confirmed",
                "usage": "consumed",
                "verification": verification,
                "recovery": {
                    "outcome": "not_needed",
                    "attempted": False,
                    "manualActionRequired": False,
                },
                "retrySafe": False,
                "result": {
                    "actionId": record.context["actionId"],
                    "actionContractVersion": record.descriptor.version,
                    "value": result,
                },
            }
        except Exception as failure:
            self._observe_private_failure(record, failure, failure_phase)
            possible = (
                "none"
                if record.descriptor.operation_class == "read"
                else getattr(failure, "possible_mutation", "possible")
            )
            if possible == "none":
                terminal = self._failed_terminal(
                    record,
                    failure,
                    recovery={
                        "outcome": "not_needed",
                        "attempted": False,
                        "manualActionRequired": False,
                    },
                    verification=verification,
                )
            else:
                with self._lock:
                    record.state = (
                        "verification_failed_pending_recovery"
                        if isinstance(failure, PreparedActionError)
                        and failure.code == "VERIFICATION_FAILED"
                        else "execution_failed_pending_recovery"
                    )
                try:
                    with self._lock:
                        record.state = "recovering"
                    failure_phase = "descriptor.recover"
                    recovery = self._validated_recovery(
                        record.descriptor.recover(
                            current_context, record.prepared, failure
                        )
                    )
                    terminal = self._failed_terminal(
                        record,
                        failure,
                        recovery=recovery,
                        verification=verification,
                        status="recovered"
                        if recovery.get("outcome") == "succeeded"
                        else "recovery_failed",
                    )
                except Exception as recovery_failure:
                    self._observe_private_failure(
                        record, recovery_failure, failure_phase,
                    )
                    terminal = self._failed_terminal(
                        record,
                        failure,
                        recovery={
                            "outcome": "failed",
                            "attempted": True,
                            "manualActionRequired": True,
                            "cause": self._cause(recovery_failure),
                        },
                        verification=verification,
                        status="recovery_failed",
                    )
        terminal = self._bounded_terminal(record, terminal)
        try:
            self._assert_terminal_schema(record, terminal)
        except Exception as schema_failure:
            terminal = self._failed_terminal(
                record,
                schema_failure,
                recovery={
                    "outcome": "failed",
                    "attempted": record.descriptor.operation_class == "mutation",
                    "manualActionRequired": record.descriptor.operation_class
                    == "mutation",
                    "cause": self._cause(schema_failure),
                },
                status=(
                    "recovery_failed"
                    if record.descriptor.operation_class == "mutation"
                    else "failed"
                ),
            )
            self._assert_terminal_schema(record, terminal)
        with self._lock:
            record.state = str(terminal["status"])
        if record.custody_key:
            try:
                self._record_idempotency_terminal(record.custody_key, terminal)
            except Exception:
                terminal = {
                    **terminal,
                    "custody": "terminal_persistence_unavailable",
                    "retrySafe": False,
                }
        return terminal

    def _observe_private_failure(
        self,
        record: _Record,
        failure: BaseException,
        phase: str,
    ) -> None:
        observer = self._private_failure_observer
        if observer is None:
            return
        try:
            observer({
                "actionId": record.context.get("actionId"),
                "operationId": record.context.get("operationId"),
                "executionId": record.context.get("executionId"),
                "phase": getattr(failure, "prepared_action_substage", phase),
                "error": failure,
            })
        except Exception:
            # Private diagnostics are best-effort and cannot affect execution.
            pass

    def recover_terminal(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        allowed = {"actionId", "idempotencyKey", "operationId", "executionId"}
        if set(request) != allowed or not all(isinstance(request.get(key), str) and request[key] for key in allowed):
            raise PreparedActionError("INVALID_REQUEST", "Prepared-action terminal recovery request is invalid.")
        if self._load_idempotency_terminal is None:
            raise PreparedActionError("RUNTIME_UNAVAILABLE", "Prepared-action terminal recovery custody is unavailable.")
        context = dict(self._runtime_context())
        custody_key = prepared_action_digest("idempotency", {
            "accountDigest": prepared_action_digest("account", context.get("localPrincipal")),
            "idempotencyKey": request["idempotencyKey"],
        })
        terminal = self._load_idempotency_terminal(custody_key)
        if terminal is None:
            return None
        exact = dict(terminal)
        if any(exact.get(key) != request[key] for key in ("actionId", "operationId", "executionId")):
            raise PreparedActionError("IDEMPOTENCY_CONFLICT", "Prepared-action terminal custody correlation drifted.")
        self._assert_public_projection(exact)
        return exact

    def revoke(self, receipt: str) -> None:
        """Revoke a prepared receipt only while execution is provably absent."""

        with self._lock:
            record = self._open(receipt)
            if record.state not in {"prepared", "authorized"}:
                raise PreparedActionError(
                    "PREPARED_ACTION_INVALID_STATE",
                    "Prepared action can no longer be revoked before execution.",
                )
            record.state = "revoked"

    def revoke_all(self) -> None:
        with self._lock:
            for record in self._records.values():
                if record.state not in {
                    "succeeded",
                    "failed",
                    "recovered",
                    "recovery_failed",
                }:
                    record.state = "revoked"

    def _prune_expired(self) -> None:
        now = self._now_ms()
        expired = [
            receipt_id
            for receipt_id, record in self._records.items()
            if record.claims["expiresAt"] <= now
        ]
        for receipt_id in expired:
            del self._records[receipt_id]

    @staticmethod
    def _assert_public_projection(value: Any) -> None:
        forbidden = {
            "argv",
            "command",
            "commandId",
            "command_id",
            "commandPath",
            "command_path",
            "args",
            "stderr",
            "stdout",
            "route",
            "routeMetadata",
            "route_metadata",
            "engine",
            "lowering",
            "preState",
            "verificationPlan",
            "recoveryPlan",
        }

        def visit(current: Any) -> None:
            if isinstance(current, dict):
                if forbidden.intersection(current):
                    raise PreparedActionError(
                        "RUNTIME_INCOMPATIBLE",
                        "A private implementation field reached the public projection.",
                    )
                for item in current.values():
                    visit(item)
            elif isinstance(current, list):
                for item in current:
                    visit(item)
            elif isinstance(current, str):
                lowered = current.lower()
                if (
                    current.startswith(("/Users/", "/home/", "/tmp/", "\\\\"))
                    or (
                        len(current) >= 3
                        and current[0].isalpha()
                        and current[1:3] in {":\\", ":/"}
                    )
                    or "cutagent_cli/" in lowered
                    or "cutagent_cli\\" in lowered
                ):
                    raise PreparedActionError(
                        "RUNTIME_INCOMPATIBLE",
                        "A private local path reached the public projection.",
                    )

        canonical_bytes(value)
        visit(value)

    def _validated_verification(self, record: _Record, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != {
            "outcome",
            "evidence",
            "protectedStatePreserved",
        }:
            raise PreparedActionError(
                "VERIFICATION_FAILED",
                "Prepared action verification evidence is invalid.",
            )
        evidence = value.get("evidence")
        if not isinstance(evidence, list) or len(evidence) > 1000:
            raise PreparedActionError(
                "VERIFICATION_FAILED",
                "Prepared action verification evidence is invalid.",
            )
        allowed_modalities = {
            "readback",
            "structural",
            "file",
            "rendered",
            "visual",
            "auditioned",
        }
        for item in evidence:
            if (
                not isinstance(item, Mapping)
                or set(item) != {"modality", "digest", "summary"}
                or item.get("modality") not in allowed_modalities
                or not isinstance(item.get("digest"), str)
                or _DIGEST_RE.fullmatch(item["digest"]) is None
                or not isinstance(item.get("summary"), str)
                or not (1 <= len(item["summary"]) <= 500)
            ):
                raise PreparedActionError(
                    "VERIFICATION_FAILED",
                    "Prepared action verification evidence is invalid.",
                )
        if value.get("outcome") not in {
            "passed",
            "failed",
            "partial",
            "not_performed",
            "manual_review_required",
        }:
            raise PreparedActionError(
                "VERIFICATION_FAILED",
                "Prepared action verification outcome is invalid.",
            )
        if (
            record.descriptor.operation_class == "mutation"
            and value.get("outcome") == "passed"
            and (not evidence or value.get("protectedStatePreserved") is not True)
        ):
            raise PreparedActionError(
                "VERIFICATION_FAILED",
                "Mutation success requires protected-state evidence.",
            )
        if (
            record.descriptor.operation_class == "mutation"
            and value.get("outcome") == "passed"
        ):
            policy = record.prepared["impact"]["verificationPolicy"]
            modalities = {item["modality"] for item in evidence}
            if (
                any(
                    modality not in modalities for modality in policy["minimumEvidence"]
                )
                or (
                    policy["requireProtectedStatePreserved"]
                    and value.get("protectedStatePreserved") is not True
                )
                or (
                    policy["protectedTargetEvidence"] == "every_declared_target"
                    and value.get("protectedStatePreserved") is not True
                )
            ):
                raise PreparedActionError(
                    "VERIFICATION_FAILED",
                    "Mutation verification omitted required protected-state evidence.",
                )
        result = dict(value)
        self._assert_public_projection(result)
        return result

    def _assert_terminal_schema(
        self, record: _Record, value: Mapping[str, Any]
    ) -> None:
        allowed = {
            "status",
            "operationId",
            "executionId",
            "actionId",
            "possibleMutation",
            "usage",
            "verification",
            "recovery",
            "retrySafe",
            "result",
            "resultOmitted",
            "failure",
            "custody",
        }
        required = allowed - {"result", "resultOmitted", "failure", "custody"}
        if (
            not isinstance(value, Mapping)
            or not required.issubset(value)
            or not set(value).issubset(allowed)
            or value.get("status")
            not in {"succeeded", "failed", "recovered", "recovery_failed"}
            or value.get("possibleMutation")
            not in {"none", "possible", "confirmed", "partial", "unknown"}
            or value.get("usage")
            not in {"not_reserved", "released", "consumed", "unknown"}
            or value.get("retrySafe") is not False
            or value.get("actionId") != record.context["actionId"]
            or (value.get("status") == "succeeded") != ("failure" not in value)
        ):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE", "Prepared terminal shape is incompatible."
            )
        for key in ("operationId", "executionId"):
            item = value.get(key)
            if (
                not isinstance(item, str)
                or not 16 <= len(item) <= 512
                or re.fullmatch(r"[A-Za-z0-9_.~-]+", item) is None
            ):
                raise PreparedActionError(
                    "RUNTIME_INCOMPATIBLE",
                    "Prepared terminal correlation is incompatible.",
                )
        verification = value.get("verification")
        self._validate_terminal_verification(verification)
        recovery = value.get("recovery")
        if (
            not isinstance(recovery, Mapping)
            or not {"outcome", "attempted", "manualActionRequired"}.issubset(recovery)
            or not set(recovery).issubset(
                {"outcome", "attempted", "manualActionRequired", "cause"}
            )
            or recovery.get("outcome")
            not in {"not_needed", "succeeded", "failed", "manual_required"}
            or not isinstance(recovery.get("attempted"), bool)
            or not isinstance(recovery.get("manualActionRequired"), bool)
            or ("cause" in recovery and not self._valid_cause(recovery["cause"]))
        ):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE", "Prepared terminal recovery is incompatible."
            )
        if value["status"] == "succeeded":
            if verification["outcome"] != "passed" or (
                value["possibleMutation"] != "none"
                and verification["protectedStatePreserved"] is not True
            ):
                raise PreparedActionError(
                    "RUNTIME_INCOMPATIBLE", "Prepared success truth is incompatible."
                )
        if "result" in value:
            result = value["result"]
            if (
                not isinstance(result, Mapping)
                or set(result) != {"actionId", "actionContractVersion", "value"}
                or result.get("actionId") != record.context["actionId"]
                or result.get("actionContractVersion") != record.descriptor.version
                or record.descriptor.validate_public_result(result.get("value"))
                is not True
            ):
                raise PreparedActionError(
                    "RUNTIME_INCOMPATIBLE", "Prepared result schema is incompatible."
                )
        if "resultOmitted" in value:
            omitted = value["resultOmitted"]
            if (
                not isinstance(omitted, Mapping)
                or set(omitted) != {"code", "digest"}
                or omitted.get("code") != "OUTPUT_LIMIT_REACHED"
                or not isinstance(omitted.get("digest"), str)
                or _DIGEST_RE.fullmatch(omitted["digest"]) is None
            ):
                raise PreparedActionError(
                    "RUNTIME_INCOMPATIBLE", "Prepared omission is incompatible."
                )
        if "failure" in value and not self._valid_failure(value["failure"]):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE", "Prepared failure is incompatible."
            )
        if len(canonical_bytes(value)) > PREPARED_ACTION_MAX_RESULT_BYTES:
            raise PreparedActionError(
                "OUTPUT_LIMIT_REACHED", "Prepared terminal exceeded its output limit."
            )

    @staticmethod
    def _validate_terminal_verification(value: Any) -> None:
        if (
            not isinstance(value, Mapping)
            or set(value) != {"outcome", "evidence", "protectedStatePreserved"}
            or value.get("outcome")
            not in {
                "passed",
                "failed",
                "partial",
                "not_performed",
                "manual_review_required",
            }
            or (
                value.get("protectedStatePreserved") is not None
                and not isinstance(value.get("protectedStatePreserved"), bool)
            )
            or not isinstance(value.get("evidence"), list)
            or len(value["evidence"]) > 1_000
        ):
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE", "Prepared verification is incompatible."
            )
        for item in value["evidence"]:
            if (
                not isinstance(item, Mapping)
                or set(item) != {"modality", "digest", "summary"}
                or item.get("modality")
                not in {
                    "readback",
                    "structural",
                    "file",
                    "rendered",
                    "visual",
                    "auditioned",
                }
                or not isinstance(item.get("digest"), str)
                or _DIGEST_RE.fullmatch(item["digest"]) is None
                or not isinstance(item.get("summary"), str)
                or not 1 <= len(item["summary"]) <= 500
            ):
                raise PreparedActionError(
                    "RUNTIME_INCOMPATIBLE", "Prepared evidence is incompatible."
                )

    @staticmethod
    def _valid_cause(value: Any) -> bool:
        return (
            isinstance(value, Mapping)
            and set(value) == {"code"}
            and isinstance(value.get("code"), str)
            and 1 <= len(value["code"]) <= 128
        )

    @classmethod
    def _valid_failure(cls, value: Any) -> bool:
        return (
            isinstance(value, Mapping)
            and set(value)
            == {
                "code",
                "kind",
                "message",
                "cause",
                "readbackRequired",
                "recoveryGuidance",
            }
            and all(
                isinstance(value.get(key), str) and 1 <= len(value[key]) <= maximum
                for key, maximum in (("code", 128), ("kind", 128), ("message", 500))
            )
            and cls._valid_cause(value.get("cause"))
            and isinstance(value.get("readbackRequired"), bool)
            and isinstance(value.get("recoveryGuidance"), list)
            and len(value["recoveryGuidance"]) <= 20
            and all(
                isinstance(item, str) and 1 <= len(item) <= 500
                for item in value["recoveryGuidance"]
            )
        )

    def _validated_recovery(self, value: Any) -> dict[str, Any]:
        if (
            not isinstance(value, Mapping)
            or set(value) != {"outcome", "attempted", "manualActionRequired"}
            or value.get("outcome") not in {"succeeded", "failed", "manual_required"}
            or value.get("attempted") is not True
            or not isinstance(value.get("manualActionRequired"), bool)
            or (
                value.get("outcome") == "succeeded"
                and value.get("manualActionRequired") is not False
            )
        ):
            raise PreparedActionError(
                "RECOVERY_FAILED", "Prepared action recovery evidence is invalid."
            )
        result = dict(value)
        self._assert_public_projection(result)
        return result

    def _bounded_terminal(
        self, record: _Record, terminal: Mapping[str, Any]
    ) -> dict[str, Any]:
        result = dict(terminal)
        self._assert_public_projection(result)
        if result.get("status") == "succeeded" and "result" in result:
            public_result = result["result"]
            public_value = (
                public_result.get("value")
                if isinstance(public_result, Mapping)
                else public_result
            )
            public_value_bytes = json.dumps(
                public_value,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            if len(public_value_bytes) > PREPARED_ACTION_PUBLIC_RESULT_MAX_BYTES:
                omitted = result.pop("result")
                result["resultOmitted"] = {
                    "code": "OUTPUT_LIMIT_REACHED",
                    "digest": prepared_action_digest("execution", omitted),
                }
        if len(canonical_bytes(result)) <= PREPARED_ACTION_MAX_RESULT_BYTES:
            return result
        if result.get("status") == "succeeded" and "result" in result:
            omitted = result.pop("result")
            result["resultOmitted"] = {
                "code": "OUTPUT_LIMIT_REACHED",
                "digest": prepared_action_digest("execution", omitted),
            }
        if len(canonical_bytes(result)) > PREPARED_ACTION_MAX_RESULT_BYTES:
            result = self._failed_terminal(
                record,
                PreparedActionError(
                    "OUTPUT_LIMIT_REACHED",
                    "Prepared action terminal output exceeded its bound.",
                ),
                recovery={
                    "outcome": "failed",
                    "attempted": True,
                    "manualActionRequired": True,
                },
                status="recovery_failed"
                if record.descriptor.operation_class == "mutation"
                else "failed",
            )
            if record.descriptor.operation_class == "read":
                result["possibleMutation"] = "none"
        return result

    def _authorization_claims(self, record: _Record) -> dict[str, Any]:
        claims = {
            key: record.claims[key]
            for key in (
                "accountDigest",
                "subscriptionDigest",
                "sessionDigest",
                "actionDigest",
                "inputDigest",
                "contractDigest",
                "capabilityDigest",
                "protocolDigest",
                "projectDigest",
                "timelineDigest",
                "targetsDigest",
                "preStateDigest",
                "impactDigest",
                "executionDigest",
                "appArtifactDigest",
                "runtimeArtifactDigest",
                "cliArtifactDigest",
                "packagedAncestryDigest",
                "expiresAt",
            )
        }
        claims["receiptDigest"] = prepared_action_digest("receipt", record.receipt)
        return claims

    def _verify_authorization(self, token: str) -> Mapping[str, Any]:
        try:
            _header, claims = _verify_signature(token)
        except AuthorizationError as exc:
            raise PreparedActionError(
                "AUTH_TOKEN_INVALID",
                "Prepared action authorization signature is invalid.",
            ) from exc
        now = int(self._now_ms() / 1000)
        if (
            claims.get("iss") != _AUTH_ISSUER
            or claims.get("aud") != _AUTH_AUDIENCE
            or claims.get("token_type") != _AUTH_TOKEN_TYPE
            or claims.get("capability") != _AUTH_CAPABILITY
            or not isinstance(claims.get("iat"), int)
            or not isinstance(claims.get("exp"), int)
            or claims["iat"] > now + 5
            or claims["exp"] <= now
            or not isinstance(claims.get("jti"), str)
            or not isinstance(claims.get("sub"), str)
        ):
            raise PreparedActionError(
                "AUTH_TOKEN_INVALID",
                "Prepared action authorization claims are invalid.",
            )
        return claims

    def _assert_current_context(
        self, record: _Record, context: Mapping[str, Any]
    ) -> None:
        current = {
            "accountDigest": prepared_action_digest("account", context["localPrincipal"]),
            "subscriptionDigest": prepared_action_digest(
                "subscription", None
            ),
            "sessionDigest": prepared_action_digest("session", context["session"]),
            "projectDigest": prepared_action_digest("project", context["project"]),
            "timelineDigest": prepared_action_digest("timeline", context["timeline"]),
            "privateBindingsDigest": prepared_action_digest(
                "private-bindings", _deep_thaw(context.get("privateBindings", {}))
            ),
        }
        artifact = context["artifacts"]
        current.update(
            {
                "protocolDigest": prepared_action_digest(
                    "protocol", artifact["protocol"]
                ),
                "appArtifactDigest": prepared_action_digest(
                    "app-artifact", artifact["app"]
                ),
                "runtimeArtifactDigest": prepared_action_digest(
                    "runtime-artifact", artifact["runtime"]
                ),
                "cliArtifactDigest": prepared_action_digest(
                    "cli-artifact", artifact["cli"]
                ),
            }
        )
        current["packagedAncestryDigest"] = prepared_action_digest(
            "packaged-ancestry",
            {
                **{
                    key: current[key]
                    for key in (
                        "appArtifactDigest",
                        "runtimeArtifactDigest",
                        "cliArtifactDigest",
                        "protocolDigest",
                    )
                },
                "runtimeManifestDigest": artifact["runtimeManifestDigest"],
            },
        )
        artifact_keys = {
            "protocolDigest",
            "appArtifactDigest",
            "runtimeArtifactDigest",
            "cliArtifactDigest",
            "packagedAncestryDigest",
        }
        if any(current[key] != record.claims[key] for key in artifact_keys):
            record.state = "revoked"
            raise PreparedActionError(
                "RUNTIME_INCOMPATIBLE", "Prepared action packaged ancestry changed."
            )
        if any(
            current[key] != record.claims[key] for key in current.keys() - artifact_keys
        ):
            record.state = "revoked"
            raise PreparedActionError(
                "PREPARED_ACTION_BINDING_MISMATCH",
                "Prepared action identity or revision changed.",
            )

    @staticmethod
    def _assert_request_context(
        request: Mapping[str, Any],
        context: Mapping[str, Any],
        private: Mapping[str, Any],
    ) -> None:
        project = context.get("project", {})
        timeline = context.get("timeline", {})
        identities = request.get("identities", {})
        revisions = request.get("revisions", {})
        expected_identities = {
            "projectLibraryId": project.get("projectLibraryId"),
            "projectId": project.get("projectId"),
            "timelineId": timeline.get("timelineId"),
            "targetIds": [target.get("stableId") for target in private["targets"]],
        }
        expected_revisions = {
            "projectLibrary": project.get("projectLibraryRevision"),
            "project": project.get("projectRevision"),
            "timeline": timeline.get("timelineRevision"),
            "targets": {
                target.get("stableId"): target.get("revision")
                for target in private["targets"]
            },
        }
        if identities != expected_identities:
            raise PreparedActionError(
                "PREPARED_ACTION_BINDING_MISMATCH",
                "Prepared action identities do not match the signed runtime.",
            )
        if revisions != expected_revisions:
            raise PreparedActionError(
                "STALE_REVISION", "Prepared action revisions are stale."
            )

    @staticmethod
    def _cause(failure: BaseException) -> dict[str, Any]:
        code = str(
            getattr(
                failure,
                "code",
                getattr(failure, "cli_error_code", "OPERATION_FAILED"),
            )
        )
        return {"code": (code or "OPERATION_FAILED")[:128]}

    def _failed_terminal(
        self,
        record: _Record,
        failure: BaseException,
        *,
        recovery: Mapping[str, Any],
        verification: Mapping[str, Any] | None = None,
        status: str = "failed",
    ) -> dict[str, Any]:
        possible_mutation = (
            "none"
            if record.descriptor.operation_class == "read"
            else str(getattr(failure, "possible_mutation", "possible"))
        )
        if possible_mutation not in {
            "none",
            "possible",
            "confirmed",
            "partial",
            "unknown",
        }:
            possible_mutation = "unknown"
        usage = str(getattr(failure, "usage", "unknown"))
        if usage not in {"not_reserved", "released", "consumed", "unknown"}:
            usage = "unknown"
        terminal_verification = (
            dict(verification)
            if verification is not None
            else {
                "outcome": "not_performed",
                "evidence": [],
                "protectedStatePreserved": None,
            }
        )
        return {
            "status": status,
            "operationId": record.context.get("operationId", "unknown"),
            "executionId": record.context.get("executionId", "unknown"),
            "actionId": record.context.get("actionId", "unknown"),
            "possibleMutation": possible_mutation,
            "usage": usage,
            "verification": terminal_verification,
            "recovery": dict(recovery),
            "retrySafe": False,
            "failure": {
                "code": self._cause(failure)["code"],
                "kind": "operation_failed",
                "message": "The prepared action did not complete.",
                "cause": self._cause(failure),
                "readbackRequired": possible_mutation != "none",
                "recoveryGuidance": [
                    "Inspect current DaVinci Resolve state before continuing."
                    if possible_mutation != "none"
                    else "Refresh the current state before retrying with a new idempotency key."
                ],
            },
        }
