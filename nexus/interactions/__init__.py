"""Durable interaction threads with explicit fail-closed authorization.

Authorization grants are a trusted-handler boundary, never a model-output
boundary. See :mod:`nexus.interactions.service` for the enforced capability
contract and transactional lifecycle semantics.
"""

from nexus.interactions.models import (
    AuthorizationDecision,
    AuthorizationPolicy,
    AuthorizationRule,
    DenialReason,
    InteractionEvent,
    InteractionEventType,
    InteractionProposal,
    InteractionSnapshot,
    InteractionStatus,
    InteractionTransition,
    ReplayedInteraction,
    TimelineAnchor,
)
from nexus.interactions.service import (
    AuthorizationRecordNotFound,
    InteractionAuthorizationDenied,
    InteractionError,
    InteractionNotFound,
    InteractionService,
    InteractionStateError,
    RecoveryCleanupHook,
    TrustedHandler,
    UntrustedHandlerError,
)

__all__ = [
    "AuthorizationDecision",
    "AuthorizationPolicy",
    "AuthorizationRecordNotFound",
    "AuthorizationRule",
    "DenialReason",
    "InteractionAuthorizationDenied",
    "InteractionError",
    "InteractionEvent",
    "InteractionEventType",
    "InteractionNotFound",
    "InteractionProposal",
    "InteractionService",
    "InteractionSnapshot",
    "InteractionStateError",
    "InteractionStatus",
    "InteractionTransition",
    "RecoveryCleanupHook",
    "ReplayedInteraction",
    "TimelineAnchor",
    "TrustedHandler",
    "UntrustedHandlerError",
]
