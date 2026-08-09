"""Transactional lifecycle API for durable interaction threads.

Trust and composition boundary
------------------------------
The sole trusted-handler capability is minted during service construction and
delivered to the composition root through a constructor callback. The service
has no post-construction capability factory. Pydantic wire or model output
cannot represent the service-local nonce, create a grant, or satisfy one.

The composition root must also provide an expected-identity resolver and an
executor vocabulary registry. The resolver receives only the stored expected
identity and has no database access. This service itself locks and reads the
canonical narrative/chunk-metadata head before every authorized state write.
Registering this infrastructure with a gameplay handler remains out of scope.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, NoReturn
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from nexus.interactions.evaluator import (
    canonical_envelope_hash,
    evaluate_authorizations,
)
from nexus.interactions.models import (
    AuthorizationDecision,
    AuthorizationEnvelope,
    AuthorizationGrantState,
    AuthorizationPolicy,
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


class InteractionError(RuntimeError):
    """Base class for typed interaction lifecycle failures."""


class InteractionNotFound(InteractionError):
    """Raised when an interaction ID has no durable record."""


class InteractionStateError(InteractionError):
    """Raised when a lifecycle method is invalid for the current status."""


class InteractionAuthorizationDenied(InteractionError):
    """Fail-closed execution denial with a machine-readable reason."""

    def __init__(self, decision: AuthorizationDecision) -> None:
        self.decision = decision
        if decision.reason is None:
            raise ValueError("authorization denial requires a typed reason")
        detail = f"interaction authorization denied: {decision.reason.value}"
        if decision.participant_entity_id is not None:
            detail += f" for participant {decision.participant_entity_id}"
        super().__init__(detail)


class UntrustedHandlerError(InteractionError):
    """Raised when a privileged API receives no valid handler capability."""


class AuthorizationRecordNotFound(InteractionError):
    """Raised when revocation cannot find an exact current-envelope grant."""


class CommandIdConflict(InteractionError):
    """Raised when a caller reuses a command UUID with different content."""


class UnknownExecutorTransition(InteractionAuthorizationDenied):
    """Typed denial for a transition outside its namespace vocabulary."""

    def __init__(self) -> None:
        super().__init__(
            AuthorizationDecision(allowed=False, reason=DenialReason.UNKNOWN_TRANSITION)
        )


class TrustedHandler:
    """Opaque capability minted only while an InteractionService is constructed."""

    __slots__ = ("identity", "_service_nonce")

    def __init__(self, identity: str, service_nonce: object) -> None:
        self.identity = identity
        self._service_nonce = service_nonce


@dataclass(frozen=True)
class NamedRecoveryCleanupHook:
    """Named transactional cleanup whose completion is durably deduplicated."""

    name: str
    callback: Callable[[Session, InteractionSnapshot], None]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("recovery cleanup hook name must not be empty")


SessionFactory = Callable[[], Session]
ExpectedIdentityResolver = Callable[[TimelineAnchor], TimelineAnchor]
EvaluationTimeProvider = Callable[[Session], datetime]
CapabilityReceiver = Callable[[TrustedHandler], None]


def _database_time(session: Session) -> datetime:
    value = session.execute(text("SELECT CURRENT_TIMESTAMP")).scalar_one()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RuntimeError("database returned an invalid interaction evaluation time")
    return value


def _stable_hash(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class InteractionService:
    """Own transactional persistence, fencing, recovery, and full replay."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        trusted_handler_identity: str,
        capability_receiver: CapabilityReceiver,
        expected_identity_resolver: ExpectedIdentityResolver,
        executor_registry: Mapping[str, Sequence[str]],
        evaluation_time_provider: EvaluationTimeProvider = _database_time,
    ) -> None:
        identity = trusted_handler_identity.strip()
        if not identity:
            raise ValueError("trusted handler identity must not be empty")
        self._session_factory = session_factory
        self._expected_identity_resolver = expected_identity_resolver
        self._executor_registry = {
            namespace: frozenset(transitions)
            for namespace, transitions in executor_registry.items()
        }
        if not self._executor_registry or any(
            not namespace or not transitions
            for namespace, transitions in self._executor_registry.items()
        ):
            raise ValueError("executor registry requires non-empty vocabularies")
        self._evaluation_time_provider = evaluation_time_provider
        self._handler_nonce = object()
        capability_receiver(TrustedHandler(identity, self._handler_nonce))

    def propose(
        self,
        caller: TrustedHandler,
        proposal: InteractionProposal,
        *,
        command_id: UUID,
    ) -> InteractionSnapshot:
        """Persist or idempotently return a proposed interaction."""
        handler = self._require_handler(caller)
        fingerprint = self._fingerprint(
            "propose", {"proposal": proposal.model_dump(mode="json")}
        )
        with self._session_factory() as session, session.begin():
            recorded = self._recorded_command(
                session, command_id=command_id, fingerprint=fingerprint
            )
            if recorded is not None:
                return InteractionSnapshot.model_validate(
                    recorded["outcome"]["snapshot"]
                )
            interaction_id = uuid4()
            now = self._evaluation_time(session)
            session.execute(
                text(
                    """
                    INSERT INTO interactions (
                        id, kind, executor_namespace, status, policy,
                        continuation_id, revision, anchor_chunk_id, timeline_id,
                        created_at, updated_at
                    ) VALUES (
                        :id, :kind, :executor_namespace, 'proposed',
                        CAST(:policy AS JSONB), :continuation_id, 1,
                        :anchor_chunk_id, :timeline_id, :now, :now
                    )
                    """
                ),
                {
                    "id": interaction_id,
                    "kind": proposal.kind,
                    "executor_namespace": proposal.executor_namespace,
                    "policy": proposal.policy.model_dump_json(),
                    "continuation_id": proposal.continuation_id,
                    "anchor_chunk_id": proposal.anchor.anchor_chunk_id,
                    "timeline_id": proposal.anchor.timeline_id,
                    "now": now,
                },
            )
            memberships: list[dict[str, Any]] = []
            for participant_id in proposal.participant_entity_ids:
                membership_id = int(
                    session.execute(
                        text(
                            """
                            INSERT INTO interaction_participants (
                                interaction_id, participant_entity_id,
                                joined_at, joined_revision
                            ) VALUES (:interaction_id, :participant_id, :now, 1)
                            RETURNING id
                            """
                        ),
                        {
                            "interaction_id": interaction_id,
                            "participant_id": participant_id,
                            "now": now,
                        },
                    ).scalar_one()
                )
                memberships.append(
                    {
                        "membership_id": membership_id,
                        "participant_entity_id": participant_id,
                        "joined_at": now.isoformat(),
                        "joined_revision": 1,
                    }
                )
            snapshot = self._snapshot(session, interaction_id)
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=InteractionEventType.PROPOSED,
                revision=1,
                occurred_at=now,
                actor_handler=handler.identity,
                command_id=command_id,
                command_step="command",
                fingerprint=fingerprint,
                payload={
                    "kind": proposal.kind,
                    "executor_namespace": proposal.executor_namespace,
                    "policy": proposal.policy.model_dump(mode="json"),
                    "continuation_id": str(proposal.continuation_id),
                    "anchor": proposal.anchor.model_dump(mode="json"),
                    "memberships": memberships,
                },
                outcome={"snapshot": snapshot.model_dump(mode="json")},
            )
            return snapshot

    def grant(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        participant_entity_id: int,
        envelope: AuthorizationEnvelope,
        expires_at: datetime,
        command_id: UUID,
    ) -> int:
        """Record one explicit exact-envelope grant, idempotently."""
        handler = self._require_handler(caller)
        self._require_aware(expires_at, "authorization expiry")
        fingerprint = self._fingerprint(
            "grant",
            {
                "interaction_id": str(interaction_id),
                "participant_entity_id": participant_entity_id,
                "envelope": envelope.model_dump(mode="json"),
                "expires_at": expires_at.isoformat(),
            },
        )
        with self._session_factory() as session, session.begin():
            recorded = self._recorded_command(
                session,
                command_id=command_id,
                fingerprint=fingerprint,
                interaction_id=interaction_id,
            )
            if recorded is not None:
                return int(recorded["outcome"]["grant_id"])
            interaction = self._locked_row(session, interaction_id)
            self._require_open(interaction)
            self._require_not_recovering(interaction)
            policy = self._validated_policy(interaction)
            rule = policy.actions.get(envelope.action)
            if rule is None:
                self._deny(DenialReason.ACTION_NOT_DECLARED)
            self._validate_envelope_transition(interaction, envelope)
            self._require_active_participant(
                session, interaction_id, participant_entity_id
            )
            now = self._evaluation_time(session)
            validity_seconds = (expires_at - now).total_seconds()
            if validity_seconds <= 0:
                raise ValueError("authorization expiry must be in the future")
            if rule is None or validity_seconds > rule.max_validity_seconds:
                maximum = rule.max_validity_seconds if rule is not None else 0
                raise ValueError(
                    f"authorization validity {validity_seconds:.6f}s exceeds "
                    f"policy maximum {maximum}s"
                )
            envelope_hash = canonical_envelope_hash(policy, envelope)
            grant_id = int(
                session.execute(
                    text(
                        """
                        INSERT INTO interaction_authorizations (
                            interaction_id, participant_entity_id, action,
                            envelope_hash, continuation_id,
                            interaction_revision, granted,
                            granted_by_handler, granted_at, expires_at
                        ) VALUES (
                            :interaction_id, :participant_id, :action,
                            :envelope_hash, :continuation_id,
                            :revision, TRUE, :handler, :now, :expires_at
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "interaction_id": interaction_id,
                        "participant_id": participant_entity_id,
                        "action": envelope.action,
                        "envelope_hash": envelope_hash,
                        "continuation_id": interaction["continuation_id"],
                        "revision": interaction["revision"],
                        "handler": handler.identity,
                        "now": now,
                        "expires_at": expires_at,
                    },
                ).scalar_one()
            )
            self._touch_updated_at(session, interaction_id, now)
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=InteractionEventType.AUTHORIZED,
                revision=int(interaction["revision"]),
                occurred_at=now,
                actor_handler=handler.identity,
                command_id=command_id,
                command_step="command",
                fingerprint=fingerprint,
                payload={
                    "state": "granted",
                    "id": grant_id,
                    "grant_id": grant_id,
                    "participant_entity_id": participant_entity_id,
                    "action": envelope.action,
                    "envelope_hash": envelope_hash,
                    "continuation_id": str(interaction["continuation_id"]),
                    "interaction_revision": int(interaction["revision"]),
                    "granted": True,
                    "granted_at": now.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "revoked_at": None,
                },
                outcome={"grant_id": grant_id},
            )
            return grant_id

    def revoke(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        participant_entity_id: int,
        envelope: AuthorizationEnvelope,
        command_id: UUID,
    ) -> tuple[int, ...]:
        """Revoke every current exact-envelope grant, idempotently."""
        handler = self._require_handler(caller)
        fingerprint = self._fingerprint(
            "revoke",
            {
                "interaction_id": str(interaction_id),
                "participant_entity_id": participant_entity_id,
                "envelope": envelope.model_dump(mode="json"),
            },
        )
        with self._session_factory() as session, session.begin():
            recorded = self._recorded_command(
                session,
                command_id=command_id,
                fingerprint=fingerprint,
                interaction_id=interaction_id,
            )
            if recorded is not None:
                return tuple(int(value) for value in recorded["outcome"]["grant_ids"])
            interaction = self._locked_row(session, interaction_id)
            self._require_open(interaction)
            self._require_not_recovering(interaction)
            policy = self._validated_policy(interaction)
            self._validate_envelope_transition(interaction, envelope)
            envelope_hash = canonical_envelope_hash(policy, envelope)
            self._require_active_participant(
                session, interaction_id, participant_entity_id
            )
            now = self._evaluation_time(session)
            grant_ids = tuple(
                int(value)
                for value in session.execute(
                    text(
                        """
                        UPDATE interaction_authorizations
                        SET revoked_at = :now, revoked_by_handler = :handler
                        WHERE interaction_id = :interaction_id
                          AND participant_entity_id = :participant_id
                          AND action = :action
                          AND envelope_hash = :envelope_hash
                          AND continuation_id = :continuation_id
                          AND interaction_revision = :revision
                          AND revoked_at IS NULL
                        RETURNING id
                        """
                    ),
                    {
                        "now": now,
                        "handler": handler.identity,
                        "interaction_id": interaction_id,
                        "participant_id": participant_entity_id,
                        "action": envelope.action,
                        "envelope_hash": envelope_hash,
                        "continuation_id": interaction["continuation_id"],
                        "revision": interaction["revision"],
                    },
                ).scalars()
            )
            if not grant_ids:
                raise AuthorizationRecordNotFound(
                    "no current exact-envelope grant for participant "
                    f"{participant_entity_id}"
                )
            self._touch_updated_at(session, interaction_id, now)
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=InteractionEventType.AUTHORIZED,
                revision=int(interaction["revision"]),
                occurred_at=now,
                actor_handler=handler.identity,
                command_id=command_id,
                command_step="command",
                fingerprint=fingerprint,
                payload={
                    "state": "revoked",
                    "grant_ids": list(grant_ids),
                    "participant_entity_id": participant_entity_id,
                    "action": envelope.action,
                    "envelope_hash": envelope_hash,
                    "revoked_at": now.isoformat(),
                },
                outcome={"grant_ids": list(grant_ids)},
            )
            return grant_ids

    def evaluate(
        self, *, interaction_id: UUID, envelope: AuthorizationEnvelope
    ) -> AuthorizationDecision:
        """Evaluate current exact-envelope grants without lifecycle mutation."""
        try:
            with self._session_factory() as session, session.begin():
                interaction = self._locked_row(session, interaction_id)
                return self._authorization_decision(session, interaction, envelope)
        except InteractionAuthorizationDenied as exc:
            return exc.decision

    def start(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        command_id: UUID,
    ) -> InteractionSnapshot:
        """Start after exact-envelope authorization and locked freshness checks."""
        return self._execute_status_change(
            caller,
            interaction_id=interaction_id,
            command_id=command_id,
            expected_status=InteractionStatus.PROPOSED,
            envelope=self._lifecycle_envelope("start"),
            event_type=InteractionEventType.STARTED,
            target_status=InteractionStatus.IN_PROGRESS,
            payload={},
            terminal=False,
        )

    def transition(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        transition: InteractionTransition,
        command_id: UUID,
    ) -> InteractionSnapshot:
        """Apply a registered typed transition after execution-time revalidation."""
        return self._execute_status_change(
            caller,
            interaction_id=interaction_id,
            command_id=command_id,
            expected_status=InteractionStatus.IN_PROGRESS,
            envelope=transition.authorization_envelope(),
            event_type=InteractionEventType.TRANSITIONED,
            target_status=InteractionStatus.IN_PROGRESS,
            payload={
                "transition_type": transition.transition_type,
                "authorization_action": transition.authorization_action,
                "payload": transition.payload,
            },
            terminal=False,
        )

    def complete(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        command_id: UUID,
    ) -> InteractionSnapshot:
        """Complete after exact-envelope authorization and locked freshness checks."""
        return self._execute_status_change(
            caller,
            interaction_id=interaction_id,
            command_id=command_id,
            expected_status=InteractionStatus.IN_PROGRESS,
            envelope=self._lifecycle_envelope("complete"),
            event_type=InteractionEventType.COMPLETED,
            target_status=InteractionStatus.COMPLETED,
            payload={},
            terminal=True,
        )

    def stop(
        self,
        *,
        interaction_id: UUID,
        participant_entity_id: int,
        command_id: UUID,
    ) -> InteractionSnapshot:
        """Stop immediately and idempotently at any current participant's request."""
        fingerprint = self._fingerprint(
            "stop",
            {
                "interaction_id": str(interaction_id),
                "participant_entity_id": participant_entity_id,
            },
        )
        with self._session_factory() as session, session.begin():
            recorded = self._recorded_command(
                session,
                command_id=command_id,
                fingerprint=fingerprint,
                interaction_id=interaction_id,
            )
            if recorded is not None:
                return InteractionSnapshot.model_validate(
                    recorded["outcome"]["snapshot"]
                )
            interaction = self._locked_row(session, interaction_id)
            self._require_open(interaction)
            self._require_active_participant(
                session, interaction_id, participant_entity_id
            )
            now = self._evaluation_time(session)
            revision = int(interaction["revision"]) + 1
            closed = self._close_memberships(session, interaction_id, now, revision)
            self._update_status(
                session,
                interaction_id=interaction_id,
                status=InteractionStatus.STOPPED,
                revision=revision,
                updated_at=now,
                clear_lease=True,
            )
            snapshot = self._snapshot(session, interaction_id)
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=InteractionEventType.STOPPED,
                revision=revision,
                occurred_at=now,
                actor_participant_entity_id=participant_entity_id,
                command_id=command_id,
                command_step="command",
                fingerprint=fingerprint,
                payload={
                    "reason": "participant_withdrawal",
                    "closed_memberships": closed,
                },
                outcome={"snapshot": snapshot.model_dump(mode="json")},
            )
            return snapshot

    def join(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        participant_entity_id: int,
        command_id: UUID,
    ) -> InteractionSnapshot:
        """Join a participant, bumping revision and invalidating prior grants."""
        handler = self._require_handler(caller)
        fingerprint = self._fingerprint(
            "join",
            {
                "interaction_id": str(interaction_id),
                "participant_entity_id": participant_entity_id,
            },
        )
        with self._session_factory() as session, session.begin():
            recorded = self._recorded_command(
                session,
                command_id=command_id,
                fingerprint=fingerprint,
                interaction_id=interaction_id,
            )
            if recorded is not None:
                return InteractionSnapshot.model_validate(
                    recorded["outcome"]["snapshot"]
                )
            interaction = self._locked_row(session, interaction_id)
            self._require_open(interaction)
            self._require_not_recovering(interaction)
            if participant_entity_id in self._active_participant_ids(
                session, interaction_id
            ):
                raise InteractionStateError("participant is already active")
            now = self._evaluation_time(session)
            revision = int(interaction["revision"]) + 1
            membership_id = int(
                session.execute(
                    text(
                        """
                        INSERT INTO interaction_participants (
                            interaction_id, participant_entity_id,
                            joined_at, joined_revision
                        ) VALUES (
                            :interaction_id, :participant_id, :now, :revision
                        ) RETURNING id
                        """
                    ),
                    {
                        "interaction_id": interaction_id,
                        "participant_id": participant_entity_id,
                        "now": now,
                        "revision": revision,
                    },
                ).scalar_one()
            )
            self._bump_revision(session, interaction_id, revision, now)
            snapshot = self._snapshot(session, interaction_id)
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=InteractionEventType.MEMBERSHIP_JOINED,
                revision=revision,
                occurred_at=now,
                actor_handler=handler.identity,
                command_id=command_id,
                command_step="command",
                fingerprint=fingerprint,
                payload={
                    "membership_id": membership_id,
                    "participant_entity_id": participant_entity_id,
                    "joined_at": now.isoformat(),
                    "joined_revision": revision,
                },
                outcome={"snapshot": snapshot.model_dump(mode="json")},
            )
            return snapshot

    def leave(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        participant_entity_id: int,
        command_id: UUID,
    ) -> InteractionSnapshot:
        """End one membership interval and invalidate prior-revision grants."""
        handler = self._require_handler(caller)
        fingerprint = self._fingerprint(
            "leave",
            {
                "interaction_id": str(interaction_id),
                "participant_entity_id": participant_entity_id,
            },
        )
        with self._session_factory() as session, session.begin():
            recorded = self._recorded_command(
                session,
                command_id=command_id,
                fingerprint=fingerprint,
                interaction_id=interaction_id,
            )
            if recorded is not None:
                return InteractionSnapshot.model_validate(
                    recorded["outcome"]["snapshot"]
                )
            interaction = self._locked_row(session, interaction_id)
            self._require_open(interaction)
            self._require_not_recovering(interaction)
            self._require_active_participant(
                session, interaction_id, participant_entity_id
            )
            now = self._evaluation_time(session)
            revision = int(interaction["revision"]) + 1
            membership_id = int(
                session.execute(
                    text(
                        """
                        UPDATE interaction_participants
                        SET left_at = :now, left_revision = :revision
                        WHERE interaction_id = :interaction_id
                          AND participant_entity_id = :participant_id
                          AND left_at IS NULL
                        RETURNING id
                        """
                    ),
                    {
                        "now": now,
                        "revision": revision,
                        "interaction_id": interaction_id,
                        "participant_id": participant_entity_id,
                    },
                ).scalar_one()
            )
            self._bump_revision(session, interaction_id, revision, now)
            snapshot = self._snapshot(session, interaction_id)
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=InteractionEventType.MEMBERSHIP_LEFT,
                revision=revision,
                occurred_at=now,
                actor_handler=handler.identity,
                command_id=command_id,
                command_step="command",
                fingerprint=fingerprint,
                payload={
                    "membership_id": membership_id,
                    "participant_entity_id": participant_entity_id,
                    "left_at": now.isoformat(),
                    "left_revision": revision,
                },
                outcome={"snapshot": snapshot.model_dump(mode="json")},
            )
            return snapshot

    def touch(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        lease_until: datetime,
        command_id: UUID,
    ) -> InteractionSnapshot:
        """Stamp or renew an explicit in-progress handler lease."""
        handler = self._require_handler(caller)
        self._require_aware(lease_until, "interaction lease")
        fingerprint = self._fingerprint(
            "touch",
            {
                "interaction_id": str(interaction_id),
                "lease_until": lease_until.isoformat(),
            },
        )
        with self._session_factory() as session, session.begin():
            recorded = self._recorded_command(
                session,
                command_id=command_id,
                fingerprint=fingerprint,
                interaction_id=interaction_id,
            )
            if recorded is not None:
                return InteractionSnapshot.model_validate(
                    recorded["outcome"]["snapshot"]
                )
            interaction = self._locked_row(session, interaction_id)
            self._require_status(interaction, InteractionStatus.IN_PROGRESS)
            if interaction["recovery_command_id"] is not None:
                raise InteractionStateError("interaction is claimed for recovery")
            now = self._evaluation_time(session)
            if lease_until <= now:
                raise ValueError("interaction lease must expire in the future")
            session.execute(
                text(
                    """
                    UPDATE interactions
                    SET lease_until = :lease_until, updated_at = :now
                    WHERE id = :interaction_id
                    """
                ),
                {
                    "lease_until": lease_until,
                    "now": now,
                    "interaction_id": interaction_id,
                },
            )
            snapshot = self._snapshot(session, interaction_id)
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=InteractionEventType.LEASE_TOUCHED,
                revision=int(interaction["revision"]),
                occurred_at=now,
                actor_handler=handler.identity,
                command_id=command_id,
                command_step="command",
                fingerprint=fingerprint,
                payload={"lease_until": lease_until.isoformat()},
                outcome={"snapshot": snapshot.model_dump(mode="json")},
            )
            return snapshot

    def recover(
        self,
        caller: TrustedHandler,
        *,
        command_id: UUID,
        cleanup_hooks: Sequence[NamedRecoveryCleanupHook] = (),
    ) -> tuple[UUID, ...]:
        """Interrupt lease-expired interactions with durable per-hook completion."""
        handler = self._require_handler(caller)
        hook_names = [hook.name for hook in cleanup_hooks]
        if len(hook_names) != len(set(hook_names)):
            raise ValueError("recovery cleanup hook names must be unique")
        fingerprint = self._fingerprint("recover", {"hook_names": hook_names})
        recovered: list[UUID] = []
        with self._session_factory() as session, session.begin():
            command_rows = self._validate_command_reuse(
                session, command_id, fingerprint
            )
            recovered.extend(
                UUID(str(value))
                for value in session.execute(
                    text(
                        """
                        SELECT interaction_id
                        FROM interaction_events
                        WHERE command_id = :command_id
                          AND command_step = 'command'
                          AND event_type = 'interrupted'
                        ORDER BY id
                        """
                    ),
                    {"command_id": command_id},
                ).scalars()
            )
            now = self._evaluation_time(session)
            if command_rows:
                candidates = tuple(
                    dict.fromkeys(row["interaction_id"] for row in command_rows)
                )
            else:
                candidates = tuple(
                    session.execute(
                        text(
                            """
                            SELECT id
                            FROM interactions
                            WHERE status = 'in_progress'
                              AND lease_until IS NOT NULL
                              AND lease_until <= :now
                            ORDER BY lease_until, id
                            FOR UPDATE SKIP LOCKED
                            """
                        ),
                        {"now": now},
                    ).scalars()
                )
            for interaction_id in candidates:
                if interaction_id in recovered:
                    continue
                claimed = session.execute(
                    text(
                        """
                        SELECT 1
                        FROM interaction_events
                        WHERE interaction_id = :interaction_id
                          AND command_id = :command_id
                          AND command_step = 'claim'
                        """
                    ),
                    {
                        "interaction_id": interaction_id,
                        "command_id": command_id,
                    },
                ).scalar_one_or_none()
                if claimed is not None:
                    continue
                session.execute(
                    text(
                        """
                        UPDATE interactions
                        SET recovery_command_id = :command_id
                        WHERE id = :interaction_id
                        """
                    ),
                    {"command_id": command_id, "interaction_id": interaction_id},
                )
                interaction = self._locked_row(session, interaction_id)
                self._append_event(
                    session,
                    interaction_id=interaction_id,
                    event_type=InteractionEventType.RECOVERY_CLAIMED,
                    revision=int(interaction["revision"]),
                    occurred_at=now,
                    actor_handler=handler.identity,
                    command_id=command_id,
                    command_step="claim",
                    fingerprint=fingerprint,
                    payload={"lease_until": interaction["lease_until"].isoformat()},
                    outcome={"claimed": True},
                )
        for interaction_id in candidates:
            if interaction_id in recovered:
                continue
            if not self._run_cleanup_hooks(
                handler=handler,
                interaction_id=interaction_id,
                command_id=command_id,
                fingerprint=fingerprint,
                cleanup_hooks=cleanup_hooks,
            ):
                continue
            with self._session_factory() as session, session.begin():
                interaction = self._locked_row(session, interaction_id)
                now = self._evaluation_time(session)
                if (
                    interaction["status"] != InteractionStatus.IN_PROGRESS.value
                    or interaction["lease_until"] is None
                    or interaction["lease_until"] > now
                ):
                    continue
                recorded = self._recorded_command(
                    session,
                    command_id=command_id,
                    fingerprint=fingerprint,
                    interaction_id=interaction_id,
                )
                if recorded is not None:
                    recovered.append(interaction_id)
                    continue
                revision = int(interaction["revision"]) + 1
                closed = self._close_memberships(session, interaction_id, now, revision)
                self._update_status(
                    session,
                    interaction_id=interaction_id,
                    status=InteractionStatus.INTERRUPTED,
                    revision=revision,
                    updated_at=now,
                    clear_lease=True,
                )
                self._append_event(
                    session,
                    interaction_id=interaction_id,
                    event_type=InteractionEventType.INTERRUPTED,
                    revision=revision,
                    occurred_at=now,
                    actor_handler=handler.identity,
                    command_id=command_id,
                    command_step="command",
                    fingerprint=fingerprint,
                    payload={
                        "reason": "expired_handler_lease",
                        "closed_memberships": closed,
                    },
                    outcome={"interaction_id": str(interaction_id)},
                )
                recovered.append(interaction_id)
        return tuple(dict.fromkeys(recovered))

    def get(self, interaction_id: UUID) -> InteractionSnapshot:
        """Read one durable interaction and its current active membership."""
        with self._session_factory() as session, session.begin():
            return self._snapshot(session, interaction_id)

    def history(self, interaction_id: UUID) -> tuple[InteractionEvent, ...]:
        """Read immutable command and lifecycle events in replay order."""
        with self._session_factory() as session, session.begin():
            if (
                session.execute(
                    text("SELECT 1 FROM interactions WHERE id = :id"),
                    {"id": interaction_id},
                ).scalar_one_or_none()
                is None
            ):
                raise InteractionNotFound(f"interaction {interaction_id} was not found")
            rows = session.execute(
                text(
                    """
                    SELECT id, interaction_id, event_type,
                           interaction_revision,
                           actor_participant_entity_id, actor_handler,
                           command_id, command_step, command_fingerprint,
                           payload, outcome, occurred_at
                    FROM interaction_events
                    WHERE interaction_id = :interaction_id
                    ORDER BY id
                    """
                ),
                {"interaction_id": interaction_id},
            ).mappings()
            return tuple(InteractionEvent.model_validate(dict(row)) for row in rows)

    def current_state(self, interaction_id: UUID) -> ReplayedInteraction:
        """Read full live membership and grant state for replay parity checks."""
        with self._session_factory() as session, session.begin():
            interaction = self._locked_row(session, interaction_id)
            memberships = self._membership_states(session, interaction_id)
            grants = self._grant_states(session, interaction_id)
            transitions = tuple(
                str(payload["transition_type"])
                for payload in session.execute(
                    text(
                        """
                        SELECT payload
                        FROM interaction_events
                        WHERE interaction_id = :interaction_id
                          AND event_type = 'transitioned'
                        ORDER BY id
                        """
                    ),
                    {"interaction_id": interaction_id},
                ).scalars()
            )
            return self._state_model(interaction, memberships, grants, transitions)

    def replay(self, interaction_id: UUID) -> ReplayedInteraction:
        """Reconstruct status, membership history, grants, lease, and transitions."""
        events = self.history(interaction_id)
        if not events or events[0].event_type is not InteractionEventType.PROPOSED:
            raise InteractionStateError("interaction has no valid proposed event")
        memberships: dict[int, MembershipHistoryState] = {}
        grants: dict[int, AuthorizationGrantState] = {}
        transitions: list[str] = []
        status = InteractionStatus.PROPOSED
        revision = 1
        lease_until: datetime | None = None
        for event in events:
            revision = event.interaction_revision
            payload = event.payload
            if event.event_type is InteractionEventType.PROPOSED:
                for item in payload["memberships"]:
                    membership_state = MembershipHistoryState.model_validate(item)
                    memberships[membership_state.membership_id] = membership_state
            elif event.event_type is InteractionEventType.AUTHORIZED:
                if payload["state"] == "granted":
                    grant_state = AuthorizationGrantState.model_validate(
                        {
                            key: payload[key]
                            for key in (
                                "id",
                                "participant_entity_id",
                                "action",
                                "envelope_hash",
                                "continuation_id",
                                "interaction_revision",
                                "granted",
                                "granted_at",
                                "expires_at",
                                "revoked_at",
                            )
                        }
                    )
                    grants[grant_state.id] = grant_state
                else:
                    revoked_at = datetime.fromisoformat(payload["revoked_at"])
                    for grant_id in payload["grant_ids"]:
                        grants[int(grant_id)] = grants[int(grant_id)].model_copy(
                            update={"revoked_at": revoked_at}
                        )
            elif event.event_type is InteractionEventType.MEMBERSHIP_JOINED:
                membership_state = MembershipHistoryState.model_validate(payload)
                memberships[membership_state.membership_id] = membership_state
            elif event.event_type is InteractionEventType.MEMBERSHIP_LEFT:
                membership_id = int(payload["membership_id"])
                memberships[membership_id] = memberships[membership_id].model_copy(
                    update={
                        "left_at": datetime.fromisoformat(payload["left_at"]),
                        "left_revision": int(payload["left_revision"]),
                    }
                )
            elif event.event_type is InteractionEventType.LEASE_TOUCHED:
                lease_until = datetime.fromisoformat(payload["lease_until"])
            elif event.event_type is InteractionEventType.STARTED:
                status = InteractionStatus.IN_PROGRESS
            elif event.event_type is InteractionEventType.TRANSITIONED:
                status = InteractionStatus.IN_PROGRESS
                transitions.append(str(payload["transition_type"]))
            elif event.event_type is InteractionEventType.COMPLETED:
                status = InteractionStatus.COMPLETED
                lease_until = None
            elif event.event_type is InteractionEventType.STOPPED:
                status = InteractionStatus.STOPPED
                lease_until = None
            elif event.event_type is InteractionEventType.INTERRUPTED:
                status = InteractionStatus.INTERRUPTED
                lease_until = None
            if "closed_memberships" in payload:
                for closed in payload["closed_memberships"]:
                    membership_id = int(closed["membership_id"])
                    memberships[membership_id] = memberships[membership_id].model_copy(
                        update={
                            "left_at": datetime.fromisoformat(closed["left_at"]),
                            "left_revision": int(closed["left_revision"]),
                        }
                    )
        membership_values = tuple(memberships[key] for key in sorted(memberships))
        return ReplayedInteraction(
            interaction_id=interaction_id,
            status=status,
            revision=revision,
            active_participant_entity_ids=tuple(
                state.participant_entity_id
                for state in membership_values
                if state.left_at is None
            ),
            membership_history=membership_values,
            grants=tuple(grants[key] for key in sorted(grants)),
            transition_types=tuple(transitions),
            lease_until=lease_until,
        )

    def _execute_status_change(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        command_id: UUID,
        expected_status: InteractionStatus,
        envelope: AuthorizationEnvelope,
        event_type: InteractionEventType,
        target_status: InteractionStatus,
        payload: dict[str, Any],
        terminal: bool,
    ) -> InteractionSnapshot:
        handler = self._require_handler(caller)
        fingerprint = self._fingerprint(
            event_type.value,
            {
                "interaction_id": str(interaction_id),
                "envelope": envelope.model_dump(mode="json"),
                "payload": payload,
            },
        )
        with self._session_factory() as session, session.begin():
            recorded = self._recorded_command(
                session,
                command_id=command_id,
                fingerprint=fingerprint,
                interaction_id=interaction_id,
            )
            if recorded is not None:
                return InteractionSnapshot.model_validate(
                    recorded["outcome"]["snapshot"]
                )
            interaction = self._locked_row(session, interaction_id)
            self._require_status(interaction, expected_status)
            self._require_not_recovering(interaction)
            decision = self._authorization_decision(session, interaction, envelope)
            if not decision.allowed:
                if decision.reason is DenialReason.UNKNOWN_TRANSITION:
                    raise UnknownExecutorTransition()
                raise InteractionAuthorizationDenied(decision)
            self._require_fresh_anchor_under_lock(session, interaction)
            now = self._evaluation_time(session)
            revision = int(interaction["revision"]) + 1
            closed = (
                self._close_memberships(session, interaction_id, now, revision)
                if terminal
                else []
            )
            self._update_status(
                session,
                interaction_id=interaction_id,
                status=target_status,
                revision=revision,
                updated_at=now,
                clear_lease=terminal,
            )
            snapshot = self._snapshot(session, interaction_id)
            event_payload = dict(payload)
            event_payload["envelope_hash"] = canonical_envelope_hash(
                self._validated_policy(interaction), envelope
            )
            if closed:
                event_payload["closed_memberships"] = closed
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=event_type,
                revision=revision,
                occurred_at=now,
                actor_handler=handler.identity,
                command_id=command_id,
                command_step="command",
                fingerprint=fingerprint,
                payload=event_payload,
                outcome={"snapshot": snapshot.model_dump(mode="json")},
            )
            return snapshot

    def _authorization_decision(
        self,
        session: Session,
        interaction: dict[str, Any],
        envelope: AuthorizationEnvelope,
    ) -> AuthorizationDecision:
        try:
            policy = self._validated_policy(interaction)
            if envelope.action not in policy.actions:
                return AuthorizationDecision(
                    allowed=False, reason=DenialReason.ACTION_NOT_DECLARED
                )
            self._validate_envelope_transition(interaction, envelope)
            participants = self._active_participant_ids(session, interaction["id"])
            if not participants:
                return AuthorizationDecision(
                    allowed=False, reason=DenialReason.MALFORMED_AUTHORIZATION
                )
            rows = [
                dict(row)
                for row in session.execute(
                    text(
                        """
                        SELECT id, participant_entity_id, action, envelope_hash,
                               continuation_id, interaction_revision, granted,
                               granted_at, expires_at, revoked_at
                        FROM interaction_authorizations
                        WHERE interaction_id = :interaction_id
                          AND action = :action
                        ORDER BY id
                        """
                    ),
                    {
                        "interaction_id": interaction["id"],
                        "action": envelope.action,
                    },
                ).mappings()
            ]
            return evaluate_authorizations(
                participant_entity_ids=participants,
                authorization_rows=rows,
                action=envelope.action,
                envelope_hash=canonical_envelope_hash(policy, envelope),
                continuation_id=interaction["continuation_id"],
                interaction_revision=int(interaction["revision"]),
                evaluated_at=self._evaluation_time(session),
            )
        except InteractionAuthorizationDenied as exc:
            return exc.decision
        except SQLAlchemyError as exc:
            raise InteractionAuthorizationDenied(
                AuthorizationDecision(
                    allowed=False, reason=DenialReason.EVALUATION_UNAVAILABLE
                )
            ) from exc

    def _require_fresh_anchor_under_lock(
        self, session: Session, interaction: dict[str, Any]
    ) -> None:
        stored = TimelineAnchor(
            anchor_chunk_id=interaction["anchor_chunk_id"],
            timeline_id=interaction["timeline_id"],
        )
        try:
            expected = self._expected_identity_resolver(stored)
            authoritative = (
                session.execute(
                    text(
                        """
                    SELECT nc.id AS anchor_chunk_id,
                           cm.world_layer::text AS timeline_id
                    FROM narrative_chunks nc
                    JOIN chunk_metadata cm ON cm.chunk_id = nc.id
                    ORDER BY nc.id DESC
                    LIMIT 1
                    FOR UPDATE OF nc, cm
                    """
                    )
                )
                .mappings()
                .one_or_none()
            )
        except Exception as exc:
            raise InteractionAuthorizationDenied(
                AuthorizationDecision(
                    allowed=False, reason=DenialReason.EVALUATION_UNAVAILABLE
                )
            ) from exc
        if authoritative is None:
            self._deny(DenialReason.EVALUATION_UNAVAILABLE)
        if authoritative["timeline_id"] != expected.timeline_id:
            self._deny(DenialReason.STALE_TIMELINE)
        if authoritative["anchor_chunk_id"] != expected.anchor_chunk_id:
            self._deny(DenialReason.STALE_ANCHOR)

    def _run_cleanup_hooks(
        self,
        *,
        handler: TrustedHandler,
        interaction_id: UUID,
        command_id: UUID,
        fingerprint: str,
        cleanup_hooks: Sequence[NamedRecoveryCleanupHook],
    ) -> bool:
        for hook in cleanup_hooks:
            with self._session_factory() as session, session.begin():
                interaction = self._locked_row(session, interaction_id)
                now = self._evaluation_time(session)
                if (
                    interaction["status"] != InteractionStatus.IN_PROGRESS.value
                    or interaction["lease_until"] is None
                    or interaction["lease_until"] > now
                ):
                    return False
                completed = session.execute(
                    text(
                        """
                        SELECT 1
                        FROM interaction_events
                        WHERE interaction_id = :interaction_id
                          AND event_type = 'cleanup_completed'
                          AND payload ->> 'hook_name' = :hook_name
                        """
                    ),
                    {
                        "interaction_id": interaction_id,
                        "hook_name": hook.name,
                    },
                ).scalar_one_or_none()
                if completed is not None:
                    continue
                snapshot = self._snapshot(session, interaction_id)
                hook.callback(session, snapshot)
                self._append_event(
                    session,
                    interaction_id=interaction_id,
                    event_type=InteractionEventType.CLEANUP_COMPLETED,
                    revision=int(interaction["revision"]),
                    occurred_at=now,
                    actor_handler=handler.identity,
                    command_id=command_id,
                    command_step=f"cleanup:{hook.name}",
                    fingerprint=fingerprint,
                    payload={"hook_name": hook.name},
                    outcome={"completed": True, "hook_name": hook.name},
                )
        return True

    def _validate_transition(
        self, interaction: dict[str, Any], transition_type: str
    ) -> None:
        vocabulary = self._executor_registry.get(interaction["executor_namespace"])
        if vocabulary is None or transition_type not in vocabulary:
            raise UnknownExecutorTransition()

    def _validate_envelope_transition(
        self, interaction: dict[str, Any], envelope: AuthorizationEnvelope
    ) -> None:
        lifecycle_type = f"lifecycle.{envelope.action}"
        if envelope.action in {"start", "complete"}:
            if envelope.transition_type != lifecycle_type or envelope.payload:
                self._deny(DenialReason.AUTHORIZATION_TERMS_CHANGED)
            return
        self._validate_transition(interaction, envelope.transition_type)

    def _recorded_command(
        self,
        session: Session,
        *,
        command_id: UUID,
        fingerprint: str,
        interaction_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        rows = self._validate_command_reuse(session, command_id, fingerprint)
        for row in rows:
            if row["command_step"] != "command":
                continue
            if interaction_id is None or row["interaction_id"] == interaction_id:
                return row
        return None

    @staticmethod
    def _validate_command_reuse(
        session: Session, command_id: UUID, fingerprint: str
    ) -> list[dict[str, Any]]:
        rows = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT interaction_id, command_step,
                           command_fingerprint, outcome
                    FROM interaction_events
                    WHERE command_id = :command_id
                    ORDER BY id
                    """
                ),
                {"command_id": command_id},
            ).mappings()
        ]
        if any(row["command_fingerprint"] != fingerprint for row in rows):
            raise CommandIdConflict(
                f"command_id {command_id} was reused with different content"
            )
        return rows

    @staticmethod
    def _fingerprint(command: str, content: dict[str, Any]) -> str:
        return _stable_hash({"command": command, "content": content})

    def _require_handler(self, caller: TrustedHandler) -> TrustedHandler:
        if not isinstance(caller, TrustedHandler):
            raise UntrustedHandlerError("privileged interaction API requires a handler")
        if caller._service_nonce is not self._handler_nonce:
            raise UntrustedHandlerError(
                "trusted handler capability belongs to a different service"
            )
        return caller

    @staticmethod
    def _deny(reason: DenialReason) -> NoReturn:
        raise InteractionAuthorizationDenied(
            AuthorizationDecision(allowed=False, reason=reason)
        )

    @staticmethod
    def _require_aware(value: datetime, label: str) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{label} must be timezone-aware")

    @staticmethod
    def _lifecycle_envelope(action: str) -> AuthorizationEnvelope:
        return AuthorizationEnvelope(
            action=action,
            transition_type=f"lifecycle.{action}",
        )

    def _validated_policy(self, interaction: dict[str, Any]) -> AuthorizationPolicy:
        try:
            return AuthorizationPolicy.model_validate(interaction["policy"])
        except (TypeError, ValueError, ValidationError) as exc:
            raise InteractionAuthorizationDenied(
                AuthorizationDecision(
                    allowed=False, reason=DenialReason.MALFORMED_POLICY
                )
            ) from exc

    @staticmethod
    def _require_open(interaction: dict[str, Any]) -> None:
        if interaction["status"] not in {
            InteractionStatus.PROPOSED.value,
            InteractionStatus.IN_PROGRESS.value,
        }:
            raise InteractionStateError(
                f"interaction {interaction['id']} is terminal: "
                f"{interaction['status']}"
            )

    @staticmethod
    def _require_status(
        interaction: dict[str, Any], expected: InteractionStatus
    ) -> None:
        if interaction["status"] != expected.value:
            raise InteractionStateError(
                f"interaction {interaction['id']} is {interaction['status']}; "
                f"expected {expected.value}"
            )

    @staticmethod
    def _require_not_recovering(interaction: dict[str, Any]) -> None:
        if interaction["recovery_command_id"] is not None:
            raise InteractionStateError("interaction is claimed for recovery")

    def _locked_row(self, session: Session, interaction_id: UUID) -> dict[str, Any]:
        row = (
            session.execute(
                text(
                    """
                SELECT id, kind, executor_namespace, status, policy,
                       continuation_id, revision, anchor_chunk_id, timeline_id,
                       lease_until, recovery_command_id, created_at, updated_at
                FROM interactions
                WHERE id = :interaction_id
                FOR UPDATE
                """
                ),
                {"interaction_id": interaction_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise InteractionNotFound(f"interaction {interaction_id} was not found")
        return dict(row)

    def _snapshot(self, session: Session, interaction_id: UUID) -> InteractionSnapshot:
        interaction = self._locked_row(session, interaction_id)
        policy = self._validated_policy(interaction)
        return InteractionSnapshot(
            id=interaction["id"],
            kind=interaction["kind"],
            executor_namespace=interaction["executor_namespace"],
            status=interaction["status"],
            policy=policy,
            continuation_id=interaction["continuation_id"],
            revision=interaction["revision"],
            anchor=TimelineAnchor(
                anchor_chunk_id=interaction["anchor_chunk_id"],
                timeline_id=interaction["timeline_id"],
            ),
            participant_entity_ids=self._active_participant_ids(
                session, interaction_id
            ),
            lease_until=interaction["lease_until"],
            created_at=interaction["created_at"],
            updated_at=interaction["updated_at"],
        )

    @staticmethod
    def _active_participant_ids(
        session: Session, interaction_id: UUID
    ) -> tuple[int, ...]:
        return tuple(
            int(value)
            for value in session.execute(
                text(
                    """
                    SELECT participant_entity_id
                    FROM interaction_participants
                    WHERE interaction_id = :interaction_id
                      AND left_at IS NULL
                    ORDER BY id
                    """
                ),
                {"interaction_id": interaction_id},
            ).scalars()
        )

    @staticmethod
    def _require_active_participant(
        session: Session, interaction_id: UUID, participant_entity_id: int
    ) -> None:
        present = session.execute(
            text(
                """
                SELECT 1
                FROM interaction_participants
                WHERE interaction_id = :interaction_id
                  AND participant_entity_id = :participant_id
                  AND left_at IS NULL
                FOR UPDATE
                """
            ),
            {
                "interaction_id": interaction_id,
                "participant_id": participant_entity_id,
            },
        ).scalar_one_or_none()
        if present is None:
            raise InteractionStateError(
                f"entity {participant_entity_id} is not a current participant"
            )

    def _evaluation_time(self, session: Session) -> datetime:
        value = self._evaluation_time_provider(session)
        self._require_aware(value, "interaction evaluation time")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _touch_updated_at(
        session: Session, interaction_id: UUID, updated_at: datetime
    ) -> None:
        session.execute(
            text("UPDATE interactions SET updated_at = :at WHERE id = :id"),
            {"at": updated_at, "id": interaction_id},
        )

    @staticmethod
    def _bump_revision(
        session: Session,
        interaction_id: UUID,
        revision: int,
        updated_at: datetime,
    ) -> None:
        session.execute(
            text(
                """
                UPDATE interactions
                SET revision = :revision, updated_at = :updated_at
                WHERE id = :interaction_id
                """
            ),
            {
                "revision": revision,
                "updated_at": updated_at,
                "interaction_id": interaction_id,
            },
        )

    @staticmethod
    def _update_status(
        session: Session,
        *,
        interaction_id: UUID,
        status: InteractionStatus,
        revision: int,
        updated_at: datetime,
        clear_lease: bool,
    ) -> None:
        session.execute(
            text(
                """
                UPDATE interactions
                SET status = :status, revision = :revision,
                    lease_until = CASE
                        WHEN :clear_lease THEN NULL ELSE lease_until
                    END,
                    recovery_command_id = CASE
                        WHEN :clear_lease THEN NULL ELSE recovery_command_id
                    END,
                    updated_at = :updated_at
                WHERE id = :interaction_id
                """
            ),
            {
                "status": status.value,
                "revision": revision,
                "updated_at": updated_at,
                "clear_lease": clear_lease,
                "interaction_id": interaction_id,
            },
        )

    @staticmethod
    def _close_memberships(
        session: Session,
        interaction_id: UUID,
        left_at: datetime,
        left_revision: int,
    ) -> list[dict[str, Any]]:
        rows = session.execute(
            text(
                """
                UPDATE interaction_participants
                SET left_at = :left_at, left_revision = :left_revision
                WHERE interaction_id = :interaction_id
                  AND left_at IS NULL
                RETURNING id, participant_entity_id
                """
            ),
            {
                "left_at": left_at,
                "left_revision": left_revision,
                "interaction_id": interaction_id,
            },
        ).mappings()
        return [
            {
                "membership_id": int(row["id"]),
                "participant_entity_id": int(row["participant_entity_id"]),
                "left_at": left_at.isoformat(),
                "left_revision": left_revision,
            }
            for row in rows
        ]

    @staticmethod
    def _append_event(
        session: Session,
        *,
        interaction_id: UUID,
        event_type: InteractionEventType,
        revision: int,
        occurred_at: datetime,
        command_id: UUID,
        command_step: str,
        fingerprint: str,
        payload: dict[str, Any],
        outcome: dict[str, Any],
        actor_participant_entity_id: int | None = None,
        actor_handler: str | None = None,
    ) -> None:
        session.execute(
            text(
                """
                INSERT INTO interaction_events (
                    interaction_id, event_type, interaction_revision,
                    actor_participant_entity_id, actor_handler,
                    command_id, command_step, command_fingerprint,
                    payload, outcome, occurred_at
                ) VALUES (
                    :interaction_id, :event_type, :revision,
                    :actor_participant_entity_id, :actor_handler,
                    :command_id, :command_step, :fingerprint,
                    CAST(:payload AS JSONB), CAST(:outcome AS JSONB), :occurred_at
                )
                """
            ),
            {
                "interaction_id": interaction_id,
                "event_type": event_type.value,
                "revision": revision,
                "actor_participant_entity_id": actor_participant_entity_id,
                "actor_handler": actor_handler,
                "command_id": command_id,
                "command_step": command_step,
                "fingerprint": fingerprint,
                "payload": json.dumps(payload),
                "outcome": json.dumps(outcome),
                "occurred_at": occurred_at,
            },
        )

    @staticmethod
    def _membership_states(
        session: Session, interaction_id: UUID
    ) -> tuple[MembershipHistoryState, ...]:
        rows = session.execute(
            text(
                """
                SELECT id AS membership_id, participant_entity_id,
                       joined_at, joined_revision, left_at, left_revision
                FROM interaction_participants
                WHERE interaction_id = :interaction_id
                ORDER BY id
                """
            ),
            {"interaction_id": interaction_id},
        ).mappings()
        return tuple(MembershipHistoryState.model_validate(dict(row)) for row in rows)

    @staticmethod
    def _grant_states(
        session: Session, interaction_id: UUID
    ) -> tuple[AuthorizationGrantState, ...]:
        rows = session.execute(
            text(
                """
                SELECT id, participant_entity_id, action, envelope_hash,
                       continuation_id, interaction_revision, granted,
                       granted_at, expires_at, revoked_at
                FROM interaction_authorizations
                WHERE interaction_id = :interaction_id
                ORDER BY id
                """
            ),
            {"interaction_id": interaction_id},
        ).mappings()
        return tuple(AuthorizationGrantState.model_validate(dict(row)) for row in rows)

    @staticmethod
    def _state_model(
        interaction: dict[str, Any],
        memberships: tuple[MembershipHistoryState, ...],
        grants: tuple[AuthorizationGrantState, ...],
        transitions: tuple[str, ...],
    ) -> ReplayedInteraction:
        return ReplayedInteraction(
            interaction_id=interaction["id"],
            status=interaction["status"],
            revision=interaction["revision"],
            active_participant_entity_ids=tuple(
                state.participant_entity_id
                for state in memberships
                if state.left_at is None
            ),
            membership_history=memberships,
            grants=grants,
            transition_types=transitions,
            lease_until=interaction["lease_until"],
        )
