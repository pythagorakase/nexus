"""Validated public data models for durable interaction threads."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)


NamespacedIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    ),
]
ActionName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        pattern=r"^[a-z][a-z0-9_.:-]*$",
    ),
]
MaterialField = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    ),
]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
EnvelopeHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InteractionStatus(str, Enum):
    """Durable lifecycle states for an interaction."""

    PROPOSED = "proposed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"


class InteractionEventType(str, Enum):
    """Append-only interaction event vocabulary."""

    PROPOSED = "proposed"
    AUTHORIZED = "authorized"
    STARTED = "started"
    TRANSITIONED = "transitioned"
    COMPLETED = "completed"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"
    MEMBERSHIP_JOINED = "membership_joined"
    MEMBERSHIP_LEFT = "membership_left"
    LEASE_TOUCHED = "lease_touched"
    RECOVERY_CLAIMED = "recovery_claimed"
    CLEANUP_COMPLETED = "cleanup_completed"


class DenialReason(str, Enum):
    """Typed fail-closed authorization, vocabulary, and freshness reasons."""

    MISSING_AUTHORIZATION = "missing_authorization"
    MALFORMED_AUTHORIZATION = "malformed_authorization"
    MALFORMED_POLICY = "malformed_policy"
    EXPIRED_AUTHORIZATION = "expired_authorization"
    REVOKED_AUTHORIZATION = "revoked_authorization"
    STALE_AUTHORIZATION = "stale_authorization"
    AUTHORIZATION_TERMS_CHANGED = "authorization_terms_changed"
    ACTION_NOT_DECLARED = "action_not_declared"
    UNKNOWN_TRANSITION = "unknown_transition"
    EVALUATION_UNAVAILABLE = "evaluation_unavailable"
    STALE_ANCHOR = "stale_anchor"
    STALE_TIMELINE = "stale_timeline"


class AuthorizationRule(_StrictModel):
    """One action's all-participant, bounded, material-term policy."""

    max_validity_seconds: int = Field(gt=0)
    material_fields: tuple[MaterialField, ...] = ()
    require_all_active_participants: Literal[True] = True

    @field_validator("material_fields")
    @classmethod
    def _material_fields_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("material payload fields must be unique")
        return value


class AuthorizationPolicy(_StrictModel):
    """Declared action policy validated again at every execution boundary."""

    actions: dict[ActionName, AuthorizationRule] = Field(min_length=1)

    @model_validator(mode="after")
    def _require_lifecycle_actions(self) -> "AuthorizationPolicy":
        missing = {"start", "complete"} - set(self.actions)
        if missing:
            raise ValueError(
                "authorization policy must declare lifecycle actions: "
                f"{sorted(missing)}"
            )
        for lifecycle_action in ("start", "complete"):
            if self.actions[lifecycle_action].material_fields:
                raise ValueError(
                    f"{lifecycle_action} cannot declare material payload fields"
                )
        return self


class TimelineAnchor(_StrictModel):
    """Expected authoritative story position for execution fencing."""

    anchor_chunk_id: int = Field(gt=0)
    timeline_id: NonEmptyText


class AuthorizationEnvelope(_StrictModel):
    """Action, transition type, and proposed terms presented for authorization."""

    action: ActionName
    transition_type: NamespacedIdentifier
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class InteractionProposal(_StrictModel):
    """Trusted-handler input for creating a proposed interaction."""

    kind: NonEmptyText
    executor_namespace: NamespacedIdentifier
    policy: AuthorizationPolicy
    participant_entity_ids: list[int] = Field(min_length=2)
    anchor: TimelineAnchor
    continuation_id: UUID = Field(default_factory=uuid4)

    @field_validator("participant_entity_ids")
    @classmethod
    def _participants_are_unique_and_positive(cls, value: list[int]) -> list[int]:
        if any(participant_id <= 0 for participant_id in value):
            raise ValueError("participant entity IDs must be positive")
        if len(set(value)) != len(value):
            raise ValueError("participant entity IDs must be unique")
        return value


class InteractionTransition(_StrictModel):
    """Typed executor transition plus the exact action that authorizes it."""

    transition_type: NamespacedIdentifier
    authorization_action: ActionName
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    def authorization_envelope(self) -> AuthorizationEnvelope:
        """Return the actual command envelope revalidated at execution."""
        return AuthorizationEnvelope(
            action=self.authorization_action,
            transition_type=self.transition_type,
            payload=self.payload,
        )


class InteractionSnapshot(_StrictModel):
    """Materialized durable state returned by lifecycle operations."""

    id: UUID
    kind: str
    executor_namespace: str
    status: InteractionStatus
    policy: AuthorizationPolicy
    continuation_id: UUID
    revision: int
    anchor: TimelineAnchor
    participant_entity_ids: tuple[int, ...]
    lease_until: datetime | None
    created_at: datetime
    updated_at: datetime


class AuthorizationDecision(_StrictModel):
    """Result of the fail-closed evaluator."""

    allowed: bool
    reason: DenialReason | None = None
    participant_entity_id: int | None = None

    @model_validator(mode="after")
    def _reason_matches_outcome(self) -> "AuthorizationDecision":
        if self.allowed and (
            self.reason is not None or self.participant_entity_id is not None
        ):
            raise ValueError("allowed decisions cannot carry denial details")
        if not self.allowed and self.reason is None:
            raise ValueError("denied decisions require a typed reason")
        return self


class AuthorizationGrantState(_StrictModel):
    """Validated database shape for one participant-specific positive grant."""

    id: int
    participant_entity_id: int
    action: ActionName
    envelope_hash: EnvelopeHash
    continuation_id: UUID
    interaction_revision: int = Field(gt=0)
    granted: Literal[True]
    granted_at: datetime
    expires_at: datetime
    revoked_at: datetime | None

    @model_validator(mode="after")
    def _bounded_interval_is_well_formed(self) -> "AuthorizationGrantState":
        timestamps = [self.granted_at, self.expires_at]
        if self.revoked_at is not None:
            timestamps.append(self.revoked_at)
        if any(
            value.tzinfo is None or value.utcoffset() is None for value in timestamps
        ):
            raise ValueError("authorization timestamps must be timezone-aware")
        if self.expires_at <= self.granted_at:
            raise ValueError("authorization expiry must follow grant time")
        if self.revoked_at is not None and self.revoked_at < self.granted_at:
            raise ValueError("authorization revocation cannot precede grant time")
        return self


class InteractionEvent(_StrictModel):
    """One immutable command or cleanup event from the lifecycle ledger."""

    id: int
    interaction_id: UUID
    event_type: InteractionEventType
    interaction_revision: int
    actor_participant_entity_id: int | None
    actor_handler: str | None
    command_id: UUID
    command_step: str
    command_fingerprint: EnvelopeHash
    payload: dict[str, Any]
    outcome: dict[str, Any]
    occurred_at: datetime


class MembershipHistoryState(_StrictModel):
    """One reconstructed participant membership interval."""

    membership_id: int
    participant_entity_id: int
    joined_at: datetime
    joined_revision: int
    left_at: datetime | None = None
    left_revision: int | None = None


class ReplayedInteraction(_StrictModel):
    """Full interaction state reconstructed from durable rows or events."""

    interaction_id: UUID
    status: InteractionStatus
    revision: int
    active_participant_entity_ids: tuple[int, ...]
    membership_history: tuple[MembershipHistoryState, ...]
    grants: tuple[AuthorizationGrantState, ...]
    transition_types: tuple[str, ...]
    lease_until: datetime | None
