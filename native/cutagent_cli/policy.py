"""Runtime policy profiles and capability negotiation helpers."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import inspect
from typing import Any, Iterable, Callable, Mapping

from .capabilities import get_capabilities
from .errors import CapabilityNegotiationFailed, PolicyDenied, ValidationError
from .authz import infer_current_command_id, verify_command_authorization_locally
from .output import (
    set_capability_context,
    set_execution_engine,
    set_policy_profile,
    set_recoverability,
    set_verification_status,
)

POLICY_PROFILES = {"read_only", "auto_edit"}
API_ENGINES = {"api_native", "fusion_native", "workaround_setting", "db_workaround", "db_direct"}
GUI_ENGINES = {"resolve_gui"}
HOSTED_ENGINES = {"hosted_api"}
KNOWN_ENGINES = API_ENGINES | GUI_ENGINES | HOSTED_ENGINES | {"not_available"}

_policy_profile: str = "auto_edit"
_prepared_action_admission: ContextVar[
    tuple[str, str, object, object, object, object, Mapping[str, Any]] | None
] = ContextVar(
    "cutagent_prepared_action_admission", default=None
)


@contextmanager
def _prepared_action_admission_scope(
    action_id: str,
    command_id: str,
    authority: object,
    handler: Callable[..., Any],
    context: Mapping[str, Any],
):
    """Private exact-command scope entered only by an admitted process authority."""

    from .sdk_prepared_action import PreparedActionAuthority

    carrier = context.get("_preparedActionCarrier") if isinstance(context, Mapping) else None
    execution_token = context.get("_preparedActionExecutionToken") \
        if isinstance(context, Mapping) else None
    binding = context.get("exactRequestBinding") if isinstance(context, Mapping) else None
    function = inspect.unwrap(handler) if callable(handler) else None
    matcher = getattr(authority, "_matches_carrier_admission", None)
    authorizes = getattr(carrier, "_authorizes_prepared_action_execution", None)
    if not isinstance(carrier, PreparedActionAuthority) \
            or not isinstance(action_id, str) or not action_id \
            or not isinstance(command_id, str) or not command_id \
            or not isinstance(binding, Mapping) \
            or not callable(matcher) or function is None \
            or not callable(authorizes) \
            or authorizes(execution_token, action_id, authority, binding) is not True \
            or matcher(action_id, command_id, function) is not True:
        raise ValidationError(
            "Prepared action admission identity lacks a matching executing carrier."
        )
    token = _prepared_action_admission.set(
        (action_id, command_id, authority, function, carrier, execution_token, binding)
    )
    try:
        yield
    finally:
        _prepared_action_admission.reset(token)


def configure_policy(profile: str | None = None) -> dict[str, Any]:
    """Configure per-process policy profile."""
    global _policy_profile

    if profile is not None:
        normalized = str(profile).strip().lower()
        if normalized not in POLICY_PROFILES:
            raise ValidationError(
                f"Invalid policy profile '{profile}'.",
                details={
                    "profile": profile,
                    "allowed": sorted(POLICY_PROFILES),
                },
            )
        _policy_profile = normalized

    set_policy_profile(_policy_profile)
    return {
        "policy_profile": _policy_profile,
    }


def get_policy_profile() -> str:
    return _policy_profile


def _carrier_issued_admission_is_active(
    admission: tuple[str, str, object, object, object, object, Mapping[str, Any]]
) -> bool:
    action_id, command_id, authority, handler, carrier, execution_token, binding = admission
    matcher = getattr(authority, "_matches_carrier_admission", None)
    authorizes = getattr(carrier, "_authorizes_prepared_action_execution", None)
    return bool(
        callable(authorizes)
        and authorizes(execution_token, action_id, authority, binding) is True
        and callable(matcher)
        and matcher(action_id, command_id, handler) is True
    )


def _is_engine_compatible(intended_engine: str, resolved_engine: str) -> bool:
    if intended_engine not in KNOWN_ENGINES or resolved_engine not in KNOWN_ENGINES:
        return False
    if intended_engine == resolved_engine:
        return True
    if intended_engine in API_ENGINES and resolved_engine in API_ENGINES:
        return True
    return False


def enforce_mutation_policy(
    capability_id: str | None,
    *,
    intended_engine: str = "api_native",
    mutating: bool = True,
) -> dict[str, Any]:
    """Enforce policy profile and capability negotiation for an operation."""
    set_policy_profile(_policy_profile)

    feature_graph = get_capabilities().get("feature_graph", {})
    capability_meta = feature_graph.get(capability_id) if capability_id else None

    if capability_id:
        status = capability_meta.get("status") if capability_meta else "unknown"
        set_capability_context(capability_id, status)
    else:
        set_capability_context(None, None)

    resolved_engine = intended_engine
    if capability_meta:
        resolved_engine = str(capability_meta.get("engine", intended_engine))
        confidence = capability_meta.get("engine_confidence")
        set_execution_engine(
            resolved_engine,
            confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
        )
        set_recoverability(str(capability_meta.get("recoverability", "manual")))
        if capability_meta.get("verification_required"):
            set_verification_status("pending_manual")
    else:
        set_execution_engine(intended_engine)

    if capability_meta:
        if not _is_engine_compatible(intended_engine, resolved_engine):
            raise CapabilityNegotiationFailed(
                "Capability engine does not match command engine route.",
                details={
                    "capability_id": capability_id,
                    "intended_engine": intended_engine,
                    "resolved_engine": resolved_engine,
                    "status": capability_meta.get("status"),
                },
            )

    if not mutating:
        return {
            "capability_id": capability_id,
            "capability_status": capability_meta.get("status") if capability_meta else "unknown",
            "engine": resolved_engine,
        }

    if _policy_profile == "read_only":
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise PolicyDenied(
            "Policy profile 'read_only' blocks mutating operations.",
            details={
                "policy_profile": _policy_profile,
                "capability_id": capability_id,
            },
        )

    admission = _prepared_action_admission.get()
    if admission is None:
        verify_command_authorization_locally(infer_current_command_id())
    elif not _carrier_issued_admission_is_active(admission):
        raise ValidationError(
            "Prepared action admission was not issued by the executing carrier."
        )

    return {
        "capability_id": capability_id,
        "capability_status": capability_meta.get("status") if capability_meta else "unknown",
        "engine": resolved_engine,
    }


def require_api_method(
    target: Any,
    method_name: str,
    *,
    capability_id: str,
    runtime_object: str,
) -> Callable[..., Any]:
    """Return a callable runtime API method or raise capability negotiation failure."""
    method = getattr(target, method_name, None)
    if callable(method):
        return method
    raise CapabilityNegotiationFailed(
        "Required runtime API method not available.",
        details={
            "capability_id": capability_id,
            "required_method": method_name,
            "runtime_object": runtime_object,
        },
    )


def require_any_api_method(
    target: Any,
    method_names: Iterable[str],
    *,
    capability_id: str,
    runtime_object: str,
) -> tuple[str, Callable[..., Any]]:
    """Return first available callable method from a candidate list or raise negotiation failure."""
    for name in method_names:
        method = getattr(target, name, None)
        if callable(method):
            return name, method
    raise CapabilityNegotiationFailed(
        "Required runtime API method not available.",
        details={
            "capability_id": capability_id,
            "required_method": list(method_names),
            "runtime_object": runtime_object,
        },
    )
