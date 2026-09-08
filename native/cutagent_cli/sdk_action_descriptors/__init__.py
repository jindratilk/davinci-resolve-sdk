"""Private SDK prepared-action descriptors.

This package is proprietary runtime input.  Public SDK artifacts receive only
the separately generated public-safe action schemas and reachability truth.
"""

from .residual_av import (
    RESIDUAL_AV_ACTION_DESCRIPTORS,
    ResidualAvActionUnadvertisedError,
    assert_residual_av_prepare_candidate,
    validate_residual_av_descriptor_packet,
)
from .residual_av_prepared_action import (
    ResidualAvExecutionAuthority,
    ResidualAvPreparedActionDescriptor,
    ResidualAvSemanticOwner,
    UNAVAILABLE_RESIDUAL_AV_ACTIONS,
    residual_av_prepared_action_contributions,
    residual_av_prepared_action_descriptors,
)
from .residual_av_handler_runtime import ResidualAvHandlerExecutionAuthority

__all__ = [
    "RESIDUAL_AV_ACTION_DESCRIPTORS",
    "ResidualAvActionUnadvertisedError",
    "assert_residual_av_prepare_candidate",
    "validate_residual_av_descriptor_packet",
    "ResidualAvPreparedActionDescriptor",
    "ResidualAvExecutionAuthority",
    "ResidualAvHandlerExecutionAuthority",
    "ResidualAvSemanticOwner",
    "UNAVAILABLE_RESIDUAL_AV_ACTIONS",
    "residual_av_prepared_action_contributions",
    "residual_av_prepared_action_descriptors",
]
