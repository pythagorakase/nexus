"""Real-PostgreSQL acceptance tests for durable interaction threads."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import psycopg2
import pytest
from psycopg2 import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from nexus.interactions import (
    AuthorizationPolicy,
    AuthorizationRule,
    DenialReason,
    InteractionAuthorizationDenied,
    InteractionEventType,
    InteractionProposal,
    InteractionService,
    InteractionSnapshot,
    InteractionStatus,
    InteractionTransition,
    TimelineAnchor,
    UntrustedHandlerError,
)
from nexus.interactions.service import TrustedHandler


pytestmark = pytest.mark.requires_postgres


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


@pytest.fixture()
def disposable_interaction_db() -> Iterator[str]:
    """Clone the template, apply migration 105 twice, then drop the clone."""
    dbname = f"nexus_test_interactions_{uuid.uuid4().hex[:12]}"
    admin = _connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier("NEXUS_template"),
                )
            )
        migration = Path("migrations/105_interaction_threads.sql").read_text()
        with _connect(dbname) as conn, conn.cursor() as cur:
            cur.execute(migration)
            cur.execute(migration)
        yield dbname
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (dbname,),
            )
            cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
            )
        admin.close()


@dataclass
class _RuntimeState:
    now: datetime
    anchor: TimelineAnchor

    def resolve_anchor(self, _session: Session) -> TimelineAnchor:
        """Return the test's current authoritative timeline position."""
        return self.anchor

    def evaluation_time(self, _session: Session) -> datetime:
        """Return the controllable evaluation time."""
        return self.now


@dataclass
class _InteractionHarness:
    engine: Engine
    session_factory: sessionmaker[Session]
    service: InteractionService
    handler: TrustedHandler
    runtime: _RuntimeState
    participant_ids: tuple[int, int]


@pytest.fixture()
def interaction_harness(
    disposable_interaction_db: str,
) -> Iterator[_InteractionHarness]:
    """Build the genuine service over a disposable migrated PostgreSQL DB."""
    engine = create_engine(
        "postgresql+psycopg2://"
        f"{os.environ.get('PGUSER', 'pythagor')}@"
        f"{os.environ.get('PGHOST', 'localhost')}:"
        f"{os.environ.get('PGPORT', '5432')}/{disposable_interaction_db}"
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session, session.begin():
        participant_ids = tuple(
            int(value)
            for value in session.execute(
                text(
                    """
                    INSERT INTO entities (kind, is_active)
                    VALUES ('character', TRUE), ('character', TRUE)
                    RETURNING id
                    """
                )
            ).scalars()
        )
        anchor_chunk_id = int(
            session.execute(
                text(
                    """
                    INSERT INTO narrative_chunks (raw_text, storyteller_text)
                    VALUES ('interaction anchor', 'interaction anchor')
                    RETURNING id
                    """
                )
            ).scalar_one()
        )

    runtime = _RuntimeState(
        now=datetime(2035, 1, 2, 3, 4, tzinfo=timezone.utc),
        anchor=TimelineAnchor(
            anchor_chunk_id=anchor_chunk_id,
            timeline_id="primary:continuity-a",
        ),
    )
    service = InteractionService(
        factory,
        freshness_resolver=runtime.resolve_anchor,
        evaluation_time_provider=runtime.evaluation_time,
    )
    harness = _InteractionHarness(
        engine=engine,
        session_factory=factory,
        service=service,
        handler=service.bind_trusted_handler("test.trusted-handler"),
        runtime=runtime,
        participant_ids=(participant_ids[0], participant_ids[1]),
    )
    try:
        yield harness
    finally:
        engine.dispose()


def _proposal(harness: _InteractionHarness) -> InteractionProposal:
    return InteractionProposal(
        kind="negotiation",
        executor_namespace="nexus.test.negotiation",
        policy=AuthorizationPolicy(
            actions={
                "start": AuthorizationRule(max_validity_seconds=120),
                "advance": AuthorizationRule(max_validity_seconds=120),
                "complete": AuthorizationRule(max_validity_seconds=120),
            }
        ),
        participant_entity_ids=list(harness.participant_ids),
        anchor=harness.runtime.anchor,
    )


def _propose(harness: _InteractionHarness) -> uuid.UUID:
    return harness.service.propose(harness.handler, _proposal(harness)).id


def _grant_all(
    harness: _InteractionHarness,
    interaction_id: uuid.UUID,
    action: str,
    *,
    validity_seconds: int = 60,
) -> None:
    expires_at = harness.runtime.now + timedelta(seconds=validity_seconds)
    for participant_id in harness.participant_ids:
        harness.service.grant(
            harness.handler,
            interaction_id=interaction_id,
            participant_entity_id=participant_id,
            action=action,
            expires_at=expires_at,
        )


def _assert_denied(
    expected_reason: DenialReason,
    operation: Any,
) -> InteractionAuthorizationDenied:
    with pytest.raises(InteractionAuthorizationDenied) as caught:
        operation()
    assert caught.value.decision.reason is expected_reason
    return caught.value


def test_each_participant_needs_an_independent_positive_grant(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id = _propose(harness)
    first, second = harness.participant_ids
    harness.service.grant(
        harness.handler,
        interaction_id=interaction_id,
        participant_entity_id=first,
        action="start",
        expires_at=harness.runtime.now + timedelta(seconds=60),
    )

    denial = _assert_denied(
        DenialReason.MISSING_AUTHORIZATION,
        lambda: harness.service.start(harness.handler, interaction_id=interaction_id),
    )
    assert denial.decision.participant_entity_id == second

    harness.service.grant(
        harness.handler,
        interaction_id=interaction_id,
        participant_entity_id=second,
        action="start",
        expires_at=harness.runtime.now + timedelta(seconds=60),
    )
    assert (
        harness.service.start(harness.handler, interaction_id=interaction_id).status
        is InteractionStatus.IN_PROGRESS
    )


def test_expired_revoked_stale_and_malformed_authorization_deny_typed(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness

    expired_id = _propose(harness)
    _grant_all(harness, expired_id, "start", validity_seconds=30)
    harness.runtime.now += timedelta(seconds=31)
    _assert_denied(
        DenialReason.EXPIRED_AUTHORIZATION,
        lambda: harness.service.start(harness.handler, interaction_id=expired_id),
    )

    revoked_id = _propose(harness)
    _grant_all(harness, revoked_id, "start")
    harness.service.revoke(
        harness.handler,
        interaction_id=revoked_id,
        participant_entity_id=harness.participant_ids[1],
        action="start",
    )
    _assert_denied(
        DenialReason.REVOKED_AUTHORIZATION,
        lambda: harness.service.start(harness.handler, interaction_id=revoked_id),
    )

    stale_id = _propose(harness)
    _grant_all(harness, stale_id, "start")
    _grant_all(harness, stale_id, "advance")
    harness.service.start(harness.handler, interaction_id=stale_id)
    _assert_denied(
        DenialReason.STALE_AUTHORIZATION,
        lambda: harness.service.transition(
            harness.handler,
            interaction_id=stale_id,
            transition=InteractionTransition(
                transition_type="negotiation.advance",
                authorization_action="advance",
            ),
        ),
    )

    malformed_id = _propose(harness)
    _grant_all(harness, malformed_id, "start")
    future_granted_at = harness.runtime.now + timedelta(seconds=10)
    future_expires_at = future_granted_at + timedelta(seconds=10)
    with harness.session_factory() as session, session.begin():
        session.execute(
            text(
                """
                UPDATE interaction_authorizations
                SET granted_at = :granted_at, expires_at = :expires_at
                WHERE interaction_id = :interaction_id
                  AND participant_entity_id = :participant_id
                  AND action = 'start'
                """
            ),
            {
                "granted_at": future_granted_at,
                "expires_at": future_expires_at,
                "interaction_id": malformed_id,
                "participant_id": harness.participant_ids[0],
            },
        )
    _assert_denied(
        DenialReason.MALFORMED_AUTHORIZATION,
        lambda: harness.service.start(harness.handler, interaction_id=malformed_id),
    )


def test_malformed_policy_and_unavailable_freshness_fail_closed(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    malformed_id = _propose(harness)
    with harness.session_factory() as session, session.begin():
        session.execute(
            text(
                """
                UPDATE interactions
                SET policy = CAST(:policy AS JSONB)
                WHERE id = :interaction_id
                """
            ),
            {
                "interaction_id": malformed_id,
                "policy": '{"actions":{"start":{"max_validity_seconds":0}}}',
            },
        )
    _assert_denied(
        DenialReason.MALFORMED_POLICY,
        lambda: harness.service.start(harness.handler, interaction_id=malformed_id),
    )

    unavailable_id = _propose(harness)
    _grant_all(harness, unavailable_id, "start")

    def unavailable(_session: Session) -> TimelineAnchor:
        raise RuntimeError("authoritative timeline store unavailable")

    unavailable_service = InteractionService(
        harness.session_factory,
        freshness_resolver=unavailable,
        evaluation_time_provider=harness.runtime.evaluation_time,
    )
    unavailable_handler = unavailable_service.bind_trusted_handler("recovery.test")
    _assert_denied(
        DenialReason.EVALUATION_UNAVAILABLE,
        lambda: unavailable_service.start(
            unavailable_handler, interaction_id=unavailable_id
        ),
    )


def test_model_shaped_input_cannot_act_as_trusted_grant_caller(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id = _propose(harness)
    with pytest.raises(UntrustedHandlerError):
        harness.service.grant(
            _proposal(harness),  # type: ignore[arg-type]
            interaction_id=interaction_id,
            participant_entity_id=harness.participant_ids[0],
            action="start",
            expires_at=harness.runtime.now + timedelta(seconds=60),
        )


def test_any_participant_can_stop_immediately_without_peer_or_handler_veto(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id = _propose(harness)
    withdrawing_participant = harness.participant_ids[1]

    stopped = harness.service.stop(
        interaction_id=interaction_id,
        participant_entity_id=withdrawing_participant,
    )

    assert stopped.status is InteractionStatus.STOPPED
    events = harness.service.history(interaction_id)
    assert [event.event_type for event in events] == [
        InteractionEventType.PROPOSED,
        InteractionEventType.STOPPED,
    ]
    assert events[-1].actor_participant_entity_id == withdrawing_participant
    assert events[-1].payload == {"reason": "participant_withdrawal"}


def test_stale_anchor_rejects_start_and_transition(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    stale_start_id = _propose(harness)
    _grant_all(harness, stale_start_id, "start")
    original_anchor = harness.runtime.anchor
    harness.runtime.anchor = TimelineAnchor(
        anchor_chunk_id=original_anchor.anchor_chunk_id + 1000,
        timeline_id=original_anchor.timeline_id,
    )
    _assert_denied(
        DenialReason.STALE_ANCHOR,
        lambda: harness.service.start(harness.handler, interaction_id=stale_start_id),
    )

    harness.runtime.anchor = original_anchor
    stale_transition_id = _propose(harness)
    _grant_all(harness, stale_transition_id, "start")
    harness.service.start(harness.handler, interaction_id=stale_transition_id)
    _grant_all(harness, stale_transition_id, "advance")
    harness.runtime.anchor = TimelineAnchor(
        anchor_chunk_id=original_anchor.anchor_chunk_id + 1000,
        timeline_id=original_anchor.timeline_id,
    )
    _assert_denied(
        DenialReason.STALE_ANCHOR,
        lambda: harness.service.transition(
            harness.handler,
            interaction_id=stale_transition_id,
            transition=InteractionTransition(
                transition_type="negotiation.counteroffer",
                authorization_action="advance",
            ),
        ),
    )


def test_recovery_interrupts_orphans_with_cleanup_exactly_once(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id = _propose(harness)
    _grant_all(harness, interaction_id, "start")
    harness.service.start(harness.handler, interaction_id=interaction_id)
    harness.runtime.now += timedelta(minutes=10)
    cleanup_calls: list[uuid.UUID] = []

    def cleanup(_session: Session, interaction: InteractionSnapshot) -> None:
        cleanup_calls.append(interaction.id)

    first = harness.service.recover(
        harness.handler,
        orphaned_before=harness.runtime.now,
        cleanup_hooks=(cleanup,),
    )
    second = harness.service.recover(
        harness.handler,
        orphaned_before=harness.runtime.now,
        cleanup_hooks=(cleanup,),
    )

    assert first == (interaction_id,)
    assert second == ()
    assert cleanup_calls == [interaction_id]
    assert harness.service.get(interaction_id).status is InteractionStatus.INTERRUPTED
    assert (
        sum(
            event.event_type is InteractionEventType.INTERRUPTED
            for event in harness.service.history(interaction_id)
        )
        == 1
    )


def test_lifecycle_events_replay_full_history(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id = _propose(harness)
    _grant_all(harness, interaction_id, "start")
    harness.service.start(harness.handler, interaction_id=interaction_id)
    _grant_all(harness, interaction_id, "advance")
    harness.service.transition(
        harness.handler,
        interaction_id=interaction_id,
        transition=InteractionTransition(
            transition_type="negotiation.counteroffer",
            authorization_action="advance",
            payload={"amount": 42, "currency": "septim"},
        ),
    )
    _grant_all(harness, interaction_id, "complete")
    harness.service.complete(harness.handler, interaction_id=interaction_id)

    events = harness.service.history(interaction_id)
    assert [event.event_type for event in events] == [
        InteractionEventType.PROPOSED,
        InteractionEventType.AUTHORIZED,
        InteractionEventType.AUTHORIZED,
        InteractionEventType.STARTED,
        InteractionEventType.AUTHORIZED,
        InteractionEventType.AUTHORIZED,
        InteractionEventType.TRANSITIONED,
        InteractionEventType.AUTHORIZED,
        InteractionEventType.AUTHORIZED,
        InteractionEventType.COMPLETED,
    ]
    assert [event.interaction_revision for event in events] == [
        1,
        1,
        1,
        2,
        2,
        2,
        3,
        3,
        3,
        4,
    ]
    assert events[6].payload == {
        "transition_type": "negotiation.counteroffer",
        "authorization_action": "advance",
        "payload": {"amount": 42, "currency": "septim"},
    }
    replayed = harness.service.replay(interaction_id)
    assert replayed.status is InteractionStatus.COMPLETED
    assert replayed.revision == 4
    assert replayed.transition_types == ("negotiation.counteroffer",)
    assert replayed.authorization_events == 6


def test_migration_comments_every_column_and_events_are_append_only(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    with harness.session_factory() as session, session.begin():
        uncommented = session.execute(
            text(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'interactions', 'interaction_participants',
                      'interaction_authorizations', 'interaction_events'
                  )
                  AND col_description(
                      (quote_ident(table_schema) || '.' ||
                       quote_ident(table_name))::regclass::oid,
                      ordinal_position
                  ) IS NULL
                ORDER BY table_name, ordinal_position
                """
            )
        ).all()
    assert uncommented == []

    interaction_id = _propose(harness)
    with pytest.raises(DBAPIError, match="append-only"):
        with harness.session_factory() as session, session.begin():
            session.execute(
                text(
                    """
                    UPDATE interaction_events
                    SET payload = CAST(:payload AS JSONB)
                    WHERE interaction_id = :interaction_id
                    """
                ),
                {"interaction_id": interaction_id, "payload": '{"tampered":true}'},
            )
