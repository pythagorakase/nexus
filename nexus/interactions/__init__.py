"""Durable interaction threads with explicit fail-closed authorization.

Authorization grants are a trusted-handler boundary, never a model-output
boundary. See :mod:`nexus.interactions.service` for the enforced capability
contract and transactional lifecycle semantics.
"""

from nexus.interactions.models import (
    AuthorizationDecision,
    AuthorizationEnvelope,
    AuthorizationPolicy,
    AuthorizationRule,
    DenialReason,
    InteractionEvent,
    InteractionEventType,
    InteractionProposal,
    InteractionSnapshot,
    InteractionStatus,
    InteractionTransition,
    MembershipHistoryState,
    ReplayedInteraction,
    TimelineAnchor,
)
from nexus.interactions.service import (
    AuthorizationRecordNotFound,
    CommandIdConflict,
    InteractionAuthorizationDenied,
    InteractionError,
    InteractionNotFound,
    InteractionService,
    InteractionStateError,
    NamedRecoveryCleanupHook,
    TrustedHandler,
    UntrustedHandlerError,
    UnknownExecutorTransition,
)

__all__ = [
    "AuthorizationDecision",
    "AuthorizationEnvelope",
    "AuthorizationPolicy",
    "AuthorizationRecordNotFound",
    "AuthorizationRule",
    "CommandIdConflict",
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
    "MembershipHistoryState",
    "NamedRecoveryCleanupHook",
    "ReplayedInteraction",
    "TimelineAnchor",
    "TrustedHandler",
    "UntrustedHandlerError",
    "UnknownExecutorTransition",
]
