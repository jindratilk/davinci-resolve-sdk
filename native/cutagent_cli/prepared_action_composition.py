"""Private production composition seam for signed SDK action descriptors."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .local_prepared_authority import LocalPreparedActionAuthority as PreparedActionAuthority
from .sdk_prepared_action import (
    FilePreparedActionIdempotencyCustody,
    FrozenPreparedActionRegistry,
    PreparedActionDescriptor,
    PreparedActionRegistry,
)


def build_prepared_action_registry(
    contributions: Iterable[tuple[str, Mapping[str, PreparedActionDescriptor]]],
) -> FrozenPreparedActionRegistry:
    """Compose domain factories once; incomplete actions stay unadvertised."""

    registry = PreparedActionRegistry()
    for contribution_name, descriptors in contributions:
        registry.register_contribution(contribution_name, descriptors)
    return registry.freeze()


def create_prepared_action_authority(
    *,
    registry: FrozenPreparedActionRegistry,
    runtime_context,
    redeem_authorization_jti,
    assert_protected_state_evidence,
    policy_public_jwk,
    custody_database_path,
    execution_authorities=None,
    private_failure_observer=None,
    now_ms=None,
) -> PreparedActionAuthority:
    """Create the production authority with mandatory durable custody."""

    custody = FilePreparedActionIdempotencyCustody(custody_database_path)
    return PreparedActionAuthority(
        registry=registry,
        runtime_context=runtime_context,
        redeem_authorization_jti=redeem_authorization_jti,
        claim_idempotency=custody.claim,
        record_idempotency_terminal=custody.record_terminal,
        load_idempotency_terminal=custody.terminal,
        assert_protected_state_evidence=assert_protected_state_evidence,
        policy_public_jwk=policy_public_jwk,
        execution_authorities=execution_authorities,
        private_failure_observer=private_failure_observer,
        now_ms=now_ms,
    )
