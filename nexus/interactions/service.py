"""Transactional lifecycle API for durable interaction threads.

Trust boundary
--------------
Only trusted, non-model handler code may call proposal, authorization, execution,
or recovery methods. A handler must first bind an opaque capability to this exact
service instance; every privileged method verifies that capability. Pydantic wire
or LLM output models cannot represent or manufacture it. Model-generated content
may be carried inside an already-authorized transition payload, but no payload,
tool result, or structured model response can create or satisfy an authorization
record. Participant ``stop`` is intentionally separate: any current participant
can stop unilaterally and immediately without a handler, peer grant, or veto path.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from nexus.interactions.evaluator import evaluate_authorizations
from nexus.interactions.models import (
    AuthorizationDecision,
    AuthorizationPolicy,
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
    """Raised when revocation cannot find a current grant record."""


class TrustedHandler:
    """Opaque capability issued by one service to one trusted handler identity."""

    __slots__ = ("identity", "_service_nonce")

    def __init__(self, identity: str, service_nonce: object) -> None:
        self.identity = identity
        self._service_nonce = service_nonce


SessionFactory = Callable[[], Session]
FreshnessResolver = Callable[[Session], TimelineAnchor]
EvaluationTimeProvider = Callable[[Session], datetime]
RecoveryCleanupHook = Callable[[Session, InteractionSnapshot], None]


def _database_time(session: Session) -> datetime:
    value = session.execute(text("SELECT CURRENT_TIMESTAMP")).scalar_one()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RuntimeError("database returned an invalid interaction evaluation time")
    return value


class InteractionService:
    """Own transactional persistence, evaluation, recovery, and history replay."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        freshness_resolver: FreshnessResolver,
        evaluation_time_provider: EvaluationTimeProvider = _database_time,
    ) -> None:
        self._session_factory = session_factory
        self._freshness_resolver = freshness_resolver
        self._evaluation_time_provider = evaluation_time_provider
        self._handler_nonce = object()

    def bind_trusted_handler(self, identity: str) -> TrustedHandler:
        """Bind trusted bootstrap code to an opaque service-local capability."""
        normalized = identity.strip()
        if not normalized:
            raise ValueError("trusted handler identity must not be empty")
        return TrustedHandler(normalized, self._handler_nonce)

    def propose(
        self, caller: TrustedHandler, proposal: InteractionProposal
    ) -> InteractionSnapshot:
        """Persist a proposed interaction, initial memberships, and first event."""
        handler = self._require_handler(caller)
        interaction_id = uuid4()
        with self._session_factory() as session, session.begin():
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
            for participant_id in proposal.participant_entity_ids:
                session.execute(
                    text(
                        """
                        INSERT INTO interaction_participants (
                            interaction_id, participant_entity_id, joined_at
                        ) VALUES (:interaction_id, :participant_id, :joined_at)
                        """
                    ),
                    {
                        "interaction_id": interaction_id,
                        "participant_id": participant_id,
                        "joined_at": now,
                    },
                )
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=InteractionEventType.PROPOSED,
                revision=1,
                occurred_at=now,
                actor_handler=handler.identity,
                payload={
                    "kind": proposal.kind,
                    "executor_namespace": proposal.executor_namespace,
                    "participant_entity_ids": proposal.participant_entity_ids,
                    "continuation_id": str(proposal.continuation_id),
                    "anchor": proposal.anchor.model_dump(mode="json"),
                },
            )
            return self._snapshot(session, interaction_id, lock=False)

    def grant(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        participant_entity_id: int,
        action: str,
        expires_at: datetime,
    ) -> int:
        """Record one explicit participant grant from trusted handler code only."""
        handler = self._require_handler(caller)
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("authorization expiry must be timezone-aware")
        with self._session_factory() as session, session.begin():
            interaction = self._locked_row(session, interaction_id)
            self._require_open(interaction)
            policy = self._validated_policy(interaction)
            rule = policy.actions.get(action)
            if rule is None:
                raise InteractionAuthorizationDenied(
                    AuthorizationDecision(
                        allowed=False, reason=DenialReason.ACTION_NOT_DECLARED
                    )
                )
            self._require_active_participant(
                session, interaction_id, participant_entity_id
            )
            now = self._evaluation_time(session)
            validity_seconds = (expires_at - now).total_seconds()
            if validity_seconds <= 0:
                raise ValueError("authorization expiry must be in the future")
            if validity_seconds > rule.max_validity_seconds:
                raise ValueError(
                    f"authorization validity {validity_seconds:.6f}s exceeds "
                    f"policy maximum {rule.max_validity_seconds}s"
                )

            session.execute(
                text(
                    """
                    UPDATE interaction_authorizations
                    SET revoked_at = :now,
                        revoked_by_handler = :handler
                    WHERE interaction_id = :interaction_id
                      AND participant_entity_id = :participant_id
                      AND action = :action
                      AND continuation_id = :continuation_id
                      AND interaction_revision = :revision
                      AND revoked_at IS NULL
                    """
                ),
                {
                    "now": now,
                    "handler": handler.identity,
                    "interaction_id": interaction_id,
                    "participant_id": participant_entity_id,
                    "action": action,
                    "continuation_id": interaction["continuation_id"],
                    "revision": interaction["revision"],
                },
            )
            grant_id = int(
                session.execute(
                    text(
                        """
                        INSERT INTO interaction_authorizations (
                            interaction_id, participant_entity_id, action,
                            continuation_id, interaction_revision, granted,
                            granted_by_handler, granted_at, expires_at
                        ) VALUES (
                            :interaction_id, :participant_id, :action,
                            :continuation_id, :revision, TRUE,
                            :handler, :granted_at, :expires_at
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "interaction_id": interaction_id,
                        "participant_id": participant_entity_id,
                        "action": action,
                        "continuation_id": interaction["continuation_id"],
                        "revision": interaction["revision"],
                        "handler": handler.identity,
                        "granted_at": now,
                        "expires_at": expires_at,
                    },
                ).scalar_one()
            )
            self._touch(session, interaction_id, now)
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=InteractionEventType.AUTHORIZED,
                revision=int(interaction["revision"]),
                occurred_at=now,
                actor_handler=handler.identity,
                payload={
                    "state": "granted",
                    "grant_id": grant_id,
                    "participant_entity_id": participant_entity_id,
                    "action": action,
                    "expires_at": expires_at.isoformat(),
                },
            )
            return grant_id

    def revoke(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        participant_entity_id: int,
        action: str,
    ) -> int:
        """Immediately revoke the latest current-revision participant grant."""
        handler = self._require_handler(caller)
        with self._session_factory() as session, session.begin():
            interaction = self._locked_row(session, interaction_id)
            self._require_open(interaction)
            self._require_active_participant(
                session, interaction_id, participant_entity_id
            )
            now = self._evaluation_time(session)
            grant_id = session.execute(
                text(
                    """
                    UPDATE interaction_authorizations
                    SET revoked_at = :now,
                        revoked_by_handler = :handler
                    WHERE id = (
                        SELECT id
                        FROM interaction_authorizations
                        WHERE interaction_id = :interaction_id
                          AND participant_entity_id = :participant_id
                          AND action = :action
                          AND continuation_id = :continuation_id
                          AND interaction_revision = :revision
                          AND revoked_at IS NULL
                        ORDER BY id DESC
                        LIMIT 1
                        FOR UPDATE
                    )
                    RETURNING id
                    """
                ),
                {
                    "now": now,
                    "handler": handler.identity,
                    "interaction_id": interaction_id,
                    "participant_id": participant_entity_id,
                    "action": action,
                    "continuation_id": interaction["continuation_id"],
                    "revision": interaction["revision"],
                },
            ).scalar_one_or_none()
            if grant_id is None:
                raise AuthorizationRecordNotFound(
                    f"no current grant for participant {participant_entity_id} "
                    f"and action {action}"
                )
            self._touch(session, interaction_id, now)
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=InteractionEventType.AUTHORIZED,
                revision=int(interaction["revision"]),
                occurred_at=now,
                actor_handler=handler.identity,
                payload={
                    "state": "revoked",
                    "grant_id": int(grant_id),
                    "participant_entity_id": participant_entity_id,
                    "action": action,
                },
            )
            return int(grant_id)

    def evaluate(self, *, interaction_id: UUID, action: str) -> AuthorizationDecision:
        """Evaluate current grants without mutating lifecycle state."""
        try:
            with self._session_factory() as session, session.begin():
                interaction = self._locked_row(session, interaction_id)
                return self._authorization_decision(session, interaction, action)
        except InteractionAuthorizationDenied as exc:
            return exc.decision

    def start(
        self, caller: TrustedHandler, *, interaction_id: UUID
    ) -> InteractionSnapshot:
        """Start transactionally after current grants and freshness revalidate."""
        return self._execute_status_change(
            caller,
            interaction_id=interaction_id,
            expected_status=InteractionStatus.PROPOSED,
            action="start",
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
    ) -> InteractionSnapshot:
        """Apply one typed executor transition after execution-time revalidation."""
        return self._execute_status_change(
            caller,
            interaction_id=interaction_id,
            expected_status=InteractionStatus.IN_PROGRESS,
            action=transition.authorization_action,
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
        self, caller: TrustedHandler, *, interaction_id: UUID
    ) -> InteractionSnapshot:
        """Complete transactionally after current grants and freshness revalidate."""
        return self._execute_status_change(
            caller,
            interaction_id=interaction_id,
            expected_status=InteractionStatus.IN_PROGRESS,
            action="complete",
            event_type=InteractionEventType.COMPLETED,
            target_status=InteractionStatus.COMPLETED,
            payload={},
            terminal=True,
        )

    def stop(
        self, *, interaction_id: UUID, participant_entity_id: int
    ) -> InteractionSnapshot:
        """Stop immediately at any current participant's unilateral request."""
        with self._session_factory() as session, session.begin():
            interaction = self._locked_row(session, interaction_id)
            self._require_open(interaction)
            self._require_active_participant(
                session, interaction_id, participant_entity_id
            )
            now = self._evaluation_time(session)
            revision = int(interaction["revision"]) + 1
            self._update_status(
                session,
                interaction_id=interaction_id,
                status=InteractionStatus.STOPPED,
                revision=revision,
                updated_at=now,
            )
            self._close_memberships(session, interaction_id, now)
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=InteractionEventType.STOPPED,
                revision=revision,
                occurred_at=now,
                actor_participant_entity_id=participant_entity_id,
                payload={"reason": "participant_withdrawal"},
            )
            return self._snapshot(session, interaction_id, lock=False)

    def recover(
        self,
        caller: TrustedHandler,
        *,
        orphaned_before: datetime,
        cleanup_hooks: Sequence[RecoveryCleanupHook] = (),
    ) -> tuple[UUID, ...]:
        """Interrupt orphaned in-progress threads exactly once; never resume them."""
        handler = self._require_handler(caller)
        if orphaned_before.tzinfo is None or orphaned_before.utcoffset() is None:
            raise ValueError("orphan recovery cutoff must be timezone-aware")
        recovered: list[UUID] = []
        with self._session_factory() as session, session.begin():
            interaction_ids = tuple(
                session.execute(
                    text(
                        """
                        SELECT id
                        FROM interactions
                        WHERE status = 'in_progress'
                          AND updated_at < :orphaned_before
                        ORDER BY updated_at, id
                        FOR UPDATE SKIP LOCKED
                        """
                    ),
                    {"orphaned_before": orphaned_before},
                ).scalars()
            )
            for interaction_id in interaction_ids:
                snapshot = self._snapshot(session, interaction_id, lock=False)
                for cleanup_hook in cleanup_hooks:
                    cleanup_hook(session, snapshot)
                now = self._evaluation_time(session)
                revision = snapshot.revision + 1
                self._update_status(
                    session,
                    interaction_id=interaction_id,
                    status=InteractionStatus.INTERRUPTED,
                    revision=revision,
                    updated_at=now,
                )
                self._close_memberships(session, interaction_id, now)
                self._append_event(
                    session,
                    interaction_id=interaction_id,
                    event_type=InteractionEventType.INTERRUPTED,
                    revision=revision,
                    occurred_at=now,
                    actor_handler=handler.identity,
                    payload={"reason": "orphan_recovery"},
                )
                recovered.append(interaction_id)
        return tuple(recovered)

    def get(self, interaction_id: UUID) -> InteractionSnapshot:
        """Read one durable interaction and its current active membership."""
        with self._session_factory() as session, session.begin():
            return self._snapshot(session, interaction_id, lock=False)

    def history(self, interaction_id: UUID) -> tuple[InteractionEvent, ...]:
        """Read immutable lifecycle events in replay order."""
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
                           payload, occurred_at
                    FROM interaction_events
                    WHERE interaction_id = :interaction_id
                    ORDER BY id
                    """
                ),
                {"interaction_id": interaction_id},
            ).mappings()
            return tuple(InteractionEvent.model_validate(dict(row)) for row in rows)

    def replay(self, interaction_id: UUID) -> ReplayedInteraction:
        """Reconstruct lifecycle state exclusively from the append-only ledger."""
        events = self.history(interaction_id)
        if not events or events[0].event_type is not InteractionEventType.PROPOSED:
            raise InteractionStateError(
                f"interaction {interaction_id} has no valid proposed event"
            )
        status = InteractionStatus.PROPOSED
        transitions: list[str] = []
        authorization_events = 0
        revision = events[0].interaction_revision
        for event in events[1:]:
            revision = event.interaction_revision
            if event.event_type is InteractionEventType.AUTHORIZED:
                authorization_events += 1
            elif event.event_type is InteractionEventType.STARTED:
                if status is not InteractionStatus.PROPOSED:
                    raise InteractionStateError("started event followed invalid state")
                status = InteractionStatus.IN_PROGRESS
            elif event.event_type is InteractionEventType.TRANSITIONED:
                if status is not InteractionStatus.IN_PROGRESS:
                    raise InteractionStateError(
                        "transitioned event followed invalid state"
                    )
                transition_type = event.payload.get("transition_type")
                if not isinstance(transition_type, str) or not transition_type:
                    raise InteractionStateError("transition event payload is malformed")
                transitions.append(transition_type)
            elif event.event_type is InteractionEventType.COMPLETED:
                if status is not InteractionStatus.IN_PROGRESS:
                    raise InteractionStateError(
                        "completed event followed invalid state"
                    )
                status = InteractionStatus.COMPLETED
            elif event.event_type is InteractionEventType.STOPPED:
                if status not in {
                    InteractionStatus.PROPOSED,
                    InteractionStatus.IN_PROGRESS,
                }:
                    raise InteractionStateError("stopped event followed invalid state")
                status = InteractionStatus.STOPPED
            elif event.event_type is InteractionEventType.INTERRUPTED:
                if status is not InteractionStatus.IN_PROGRESS:
                    raise InteractionStateError(
                        "interrupted event followed invalid state"
                    )
                status = InteractionStatus.INTERRUPTED
            elif event.event_type is InteractionEventType.PROPOSED:
                raise InteractionStateError("duplicate proposed event")
        return ReplayedInteraction(
            interaction_id=interaction_id,
            status=status,
            revision=revision,
            transition_types=tuple(transitions),
            authorization_events=authorization_events,
        )

    def _execute_status_change(
        self,
        caller: TrustedHandler,
        *,
        interaction_id: UUID,
        expected_status: InteractionStatus,
        action: str,
        event_type: InteractionEventType,
        target_status: InteractionStatus,
        payload: dict[str, Any],
        terminal: bool,
    ) -> InteractionSnapshot:
        handler = self._require_handler(caller)
        with self._session_factory() as session, session.begin():
            interaction = self._locked_row(session, interaction_id)
            self._require_status(interaction, expected_status)
            decision = self._authorization_decision(session, interaction, action)
            if not decision.allowed:
                raise InteractionAuthorizationDenied(decision)
            self._require_fresh_anchor(session, interaction)
            now = self._evaluation_time(session)
            revision = int(interaction["revision"]) + 1
            self._update_status(
                session,
                interaction_id=interaction_id,
                status=target_status,
                revision=revision,
                updated_at=now,
            )
            if terminal:
                self._close_memberships(session, interaction_id, now)
            self._append_event(
                session,
                interaction_id=interaction_id,
                event_type=event_type,
                revision=revision,
                occurred_at=now,
                actor_handler=handler.identity,
                payload=payload,
            )
            return self._snapshot(session, interaction_id, lock=False)

    def _authorization_decision(
        self, session: Session, interaction: dict[str, Any], action: str
    ) -> AuthorizationDecision:
        try:
            policy = self._validated_policy(interaction)
            if action not in policy.actions:
                return AuthorizationDecision(
                    allowed=False, reason=DenialReason.ACTION_NOT_DECLARED
                )
            participant_ids = self._active_participant_ids(session, interaction["id"])
            if not participant_ids:
                return AuthorizationDecision(
                    allowed=False, reason=DenialReason.MALFORMED_AUTHORIZATION
                )
            rows = [
                dict(row)
                for row in session.execute(
                    text(
                        """
                        SELECT id, participant_entity_id, action,
                               continuation_id, interaction_revision, granted,
                               granted_at, expires_at, revoked_at
                        FROM interaction_authorizations
                        WHERE interaction_id = :interaction_id
                          AND action = :action
                        ORDER BY id
                        """
                    ),
                    {"interaction_id": interaction["id"], "action": action},
                ).mappings()
            ]
            return evaluate_authorizations(
                participant_entity_ids=participant_ids,
                authorization_rows=rows,
                action=action,
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

    def _require_fresh_anchor(
        self, session: Session, interaction: dict[str, Any]
    ) -> None:
        try:
            current = self._freshness_resolver(session)
        except Exception as exc:
            raise InteractionAuthorizationDenied(
                AuthorizationDecision(
                    allowed=False, reason=DenialReason.EVALUATION_UNAVAILABLE
                )
            ) from exc
        if current.timeline_id != interaction["timeline_id"]:
            raise InteractionAuthorizationDenied(
                AuthorizationDecision(allowed=False, reason=DenialReason.STALE_TIMELINE)
            )
        if current.anchor_chunk_id != interaction["anchor_chunk_id"]:
            raise InteractionAuthorizationDenied(
                AuthorizationDecision(allowed=False, reason=DenialReason.STALE_ANCHOR)
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

    def _require_handler(self, caller: TrustedHandler) -> TrustedHandler:
        if not isinstance(caller, TrustedHandler):
            raise UntrustedHandlerError("privileged interaction API requires a handler")
        if caller._service_nonce is not self._handler_nonce:
            raise UntrustedHandlerError(
                "trusted handler capability belongs to a different service"
            )
        return caller

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

    def _locked_row(self, session: Session, interaction_id: UUID) -> dict[str, Any]:
        row = (
            session.execute(
                text(
                    """
                SELECT id, kind, executor_namespace, status, policy,
                       continuation_id, revision, anchor_chunk_id, timeline_id,
                       created_at, updated_at
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

    def _snapshot(
        self, session: Session, interaction_id: UUID, *, lock: bool
    ) -> InteractionSnapshot:
        suffix = " FOR UPDATE" if lock else ""
        row = (
            session.execute(
                text(
                    """
                SELECT id, kind, executor_namespace, status, policy,
                       continuation_id, revision, anchor_chunk_id, timeline_id,
                       created_at, updated_at
                FROM interactions
                WHERE id = :interaction_id
                """
                    + suffix
                ),
                {"interaction_id": interaction_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise InteractionNotFound(f"interaction {interaction_id} was not found")
        interaction = dict(row)
        try:
            policy = AuthorizationPolicy.model_validate(interaction["policy"])
        except ValidationError as exc:
            raise InteractionAuthorizationDenied(
                AuthorizationDecision(
                    allowed=False, reason=DenialReason.MALFORMED_POLICY
                )
            ) from exc
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
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("interaction evaluation time must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _touch(session: Session, interaction_id: UUID, updated_at: datetime) -> None:
        session.execute(
            text("UPDATE interactions SET updated_at = :at WHERE id = :id"),
            {"at": updated_at, "id": interaction_id},
        )

    @staticmethod
    def _update_status(
        session: Session,
        *,
        interaction_id: UUID,
        status: InteractionStatus,
        revision: int,
        updated_at: datetime,
    ) -> None:
        session.execute(
            text(
                """
                UPDATE interactions
                SET status = :status,
                    revision = :revision,
                    updated_at = :updated_at
                WHERE id = :interaction_id
                """
            ),
            {
                "status": status.value,
                "revision": revision,
                "updated_at": updated_at,
                "interaction_id": interaction_id,
            },
        )

    @staticmethod
    def _close_memberships(
        session: Session, interaction_id: UUID, left_at: datetime
    ) -> None:
        session.execute(
            text(
                """
                UPDATE interaction_participants
                SET left_at = :left_at
                WHERE interaction_id = :interaction_id
                  AND left_at IS NULL
                """
            ),
            {"left_at": left_at, "interaction_id": interaction_id},
        )

    @staticmethod
    def _append_event(
        session: Session,
        *,
        interaction_id: UUID,
        event_type: InteractionEventType,
        revision: int,
        occurred_at: datetime,
        payload: dict[str, Any],
        actor_participant_entity_id: int | None = None,
        actor_handler: str | None = None,
    ) -> None:
        session.execute(
            text(
                """
                INSERT INTO interaction_events (
                    interaction_id, event_type, interaction_revision,
                    actor_participant_entity_id, actor_handler,
                    payload, occurred_at
                ) VALUES (
                    :interaction_id, :event_type, :revision,
                    :actor_participant_entity_id, :actor_handler,
                    CAST(:payload AS JSONB), :occurred_at
                )
                """
            ),
            {
                "interaction_id": interaction_id,
                "event_type": event_type.value,
                "revision": revision,
                "actor_participant_entity_id": actor_participant_entity_id,
                "actor_handler": actor_handler,
                "payload": json.dumps(payload),
                "occurred_at": occurred_at,
            },
        )
