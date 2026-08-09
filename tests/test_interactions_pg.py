"""Public-API PostgreSQL acceptance tests for interaction threads."""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import psycopg2
import pytest
from psycopg2 import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from nexus.interactions import (
    AuthorizationEnvelope,
    AuthorizationPolicy,
    AuthorizationRule,
    CommandIdConflict,
    DenialReason,
    InteractionAuthorizationDenied,
    InteractionEventType,
    InteractionProposal,
    InteractionService,
    InteractionSnapshot,
    InteractionStatus,
    InteractionTransition,
    NamedRecoveryCleanupHook,
    TimelineAnchor,
    TrustedHandler,
    UnknownExecutorTransition,
    UntrustedHandlerError,
)


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
class _InteractionHarness:
    engine: Engine
    session_factory: sessionmaker[Session]
    service: InteractionService
    handler: TrustedHandler
    participant_ids: tuple[int, int, int]
    anchor: TimelineAnchor


def _seed_anchor(session: Session, *, scene: int) -> TimelineAnchor:
    chunk_id = int(
        session.execute(
            text(
                """
                INSERT INTO narrative_chunks (raw_text, storyteller_text)
                VALUES (:text, :text)
                RETURNING id
                """
            ),
            {"text": f"interaction anchor {scene}"},
        ).scalar_one()
    )
    session.execute(
        text(
            """
            INSERT INTO chunk_metadata (
                chunk_id, season, episode, scene, world_layer, slug
            ) VALUES (
                :chunk_id, 1, 1, :scene, 'primary', :slug
            )
            """
        ),
        {
            "chunk_id": chunk_id,
            "scene": scene,
            "slug": f"I{scene:04d}",
        },
    )
    return TimelineAnchor(anchor_chunk_id=chunk_id, timeline_id="primary")


def _construct_service(
    factory: sessionmaker[Session],
    *,
    expected_identity: Callable[[TimelineAnchor], TimelineAnchor] | None = None,
) -> tuple[InteractionService, TrustedHandler]:
    capabilities: list[TrustedHandler] = []
    service = InteractionService(
        factory,
        trusted_handler_identity="test.trusted-handler",
        capability_receiver=capabilities.append,
        expected_identity_resolver=expected_identity or (lambda stored: stored),
        executor_registry={
            "nexus.test.negotiation": (
                "negotiation.counteroffer",
                "negotiation.accept",
            )
        },
    )
    assert len(capabilities) == 1
    return service, capabilities[0]


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
                    VALUES
                        ('character', TRUE),
                        ('character', TRUE),
                        ('character', TRUE)
                    RETURNING id
                    """
                )
            ).scalars()
        )
        anchor = _seed_anchor(session, scene=901)
    service, handler = _construct_service(factory)
    try:
        yield _InteractionHarness(
            engine=engine,
            session_factory=factory,
            service=service,
            handler=handler,
            participant_ids=(
                participant_ids[0],
                participant_ids[1],
                participant_ids[2],
            ),
            anchor=anchor,
        )
    finally:
        engine.dispose()


def _proposal(harness: _InteractionHarness) -> InteractionProposal:
    return InteractionProposal(
        kind="negotiation",
        executor_namespace="nexus.test.negotiation",
        policy=AuthorizationPolicy(
            actions={
                "start": AuthorizationRule(max_validity_seconds=120),
                "advance": AuthorizationRule(
                    max_validity_seconds=120,
                    material_fields=("amount", "currency"),
                ),
                "complete": AuthorizationRule(max_validity_seconds=120),
            }
        ),
        participant_entity_ids=list(harness.participant_ids[:2]),
        anchor=harness.anchor,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _propose(
    harness: _InteractionHarness, *, command_id: uuid.UUID | None = None
) -> tuple[uuid.UUID, uuid.UUID]:
    command = command_id or uuid.uuid4()
    snapshot = harness.service.propose(
        harness.handler,
        _proposal(harness),
        command_id=command,
    )
    return snapshot.id, command


def _start(
    harness: _InteractionHarness,
    interaction_id: uuid.UUID,
    *,
    command_id: uuid.UUID | None = None,
    lease_seconds: float = 60,
) -> InteractionSnapshot:
    return harness.service.start(
        harness.handler,
        interaction_id=interaction_id,
        lease_until=_utc_now() + timedelta(seconds=lease_seconds),
        command_id=command_id or uuid.uuid4(),
    )


def _lifecycle_envelope(action: str) -> AuthorizationEnvelope:
    return AuthorizationEnvelope(
        action=action,
        transition_type=f"lifecycle.{action}",
    )


def _transition(*, amount: int = 42, currency: str = "septim") -> InteractionTransition:
    return InteractionTransition(
        transition_type="negotiation.counteroffer",
        authorization_action="advance",
        payload={"amount": amount, "currency": currency, "flavor": "non-material"},
    )


def _grant_all(
    harness: _InteractionHarness,
    interaction_id: uuid.UUID,
    envelope: AuthorizationEnvelope,
    *,
    participant_ids: tuple[int, ...] | None = None,
    validity_seconds: float = 60,
) -> tuple[int, ...]:
    grants: list[int] = []
    for participant_id in participant_ids or harness.participant_ids[:2]:
        grants.append(
            harness.service.grant(
                harness.handler,
                interaction_id=interaction_id,
                participant_entity_id=participant_id,
                envelope=envelope,
                expires_at=_utc_now() + timedelta(seconds=validity_seconds),
                command_id=uuid.uuid4(),
            )
        )
    return tuple(grants)


def _assert_denied(
    expected_reason: DenialReason,
    operation: Callable[[], object],
) -> InteractionAuthorizationDenied:
    with pytest.raises(InteractionAuthorizationDenied) as caught:
        operation()
    assert caught.value.decision.reason is expected_reason
    return caught.value


def test_independent_grants_and_fail_closed_states(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    start_envelope = _lifecycle_envelope("start")
    interaction_id, _ = _propose(harness)
    first, second = harness.participant_ids[:2]
    harness.service.grant(
        harness.handler,
        interaction_id=interaction_id,
        participant_entity_id=first,
        envelope=start_envelope,
        expires_at=_utc_now() + timedelta(seconds=30),
        command_id=uuid.uuid4(),
    )
    denial = _assert_denied(
        DenialReason.MISSING_AUTHORIZATION,
        lambda: _start(harness, interaction_id),
    )
    assert denial.decision.participant_entity_id == second

    harness.service.grant(
        harness.handler,
        interaction_id=interaction_id,
        participant_entity_id=second,
        envelope=start_envelope,
        expires_at=_utc_now() + timedelta(seconds=0.2),
        command_id=uuid.uuid4(),
    )
    time.sleep(0.25)
    _assert_denied(
        DenialReason.EXPIRED_AUTHORIZATION,
        lambda: _start(harness, interaction_id),
    )

    revoked_id, _ = _propose(harness)
    _grant_all(harness, revoked_id, start_envelope)
    harness.service.revoke(
        harness.handler,
        interaction_id=revoked_id,
        participant_entity_id=second,
        envelope=start_envelope,
        command_id=uuid.uuid4(),
    )
    _assert_denied(
        DenialReason.REVOKED_AUTHORIZATION,
        lambda: _start(harness, revoked_id),
    )
    assert harness.service.replay(revoked_id) == harness.service.current_state(
        revoked_id
    )


def test_material_term_drift_requires_fresh_authorization(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id, _ = _propose(harness)
    _grant_all(harness, interaction_id, _lifecycle_envelope("start"))
    _start(harness, interaction_id)
    authorized = _transition(amount=42)
    _grant_all(harness, interaction_id, authorized.authorization_envelope())

    _assert_denied(
        DenialReason.AUTHORIZATION_TERMS_CHANGED,
        lambda: harness.service.transition(
            harness.handler,
            interaction_id=interaction_id,
            transition=_transition(amount=43),
            command_id=uuid.uuid4(),
        ),
    )
    changed_non_material = _transition(amount=42)
    changed_non_material.payload["flavor"] = "different but non-material"
    result = harness.service.transition(
        harness.handler,
        interaction_id=interaction_id,
        transition=changed_non_material,
        command_id=uuid.uuid4(),
    )
    assert result.status is InteractionStatus.IN_PROGRESS


def test_constructor_only_capability_and_executor_vocabulary(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    assert not hasattr(harness.service, "bind_trusted_handler")
    interaction_id, _ = _propose(harness)
    with pytest.raises(UntrustedHandlerError):
        harness.service.grant(
            _proposal(harness),  # type: ignore[arg-type]
            interaction_id=interaction_id,
            participant_entity_id=harness.participant_ids[0],
            envelope=_lifecycle_envelope("start"),
            expires_at=_utc_now() + timedelta(seconds=60),
            command_id=uuid.uuid4(),
        )

    _grant_all(harness, interaction_id, _lifecycle_envelope("start"))
    _start(harness, interaction_id)
    unknown = InteractionTransition(
        transition_type="negotiation.unregistered",
        authorization_action="advance",
        payload={"amount": 42, "currency": "septim"},
    )
    with pytest.raises(UnknownExecutorTransition) as caught:
        harness.service.transition(
            harness.handler,
            interaction_id=interaction_id,
            transition=unknown,
            command_id=uuid.uuid4(),
        )
    assert caught.value.decision.reason is DenialReason.UNKNOWN_TRANSITION


def test_command_retries_return_recorded_outcome_without_new_event(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    propose_command = uuid.uuid4()
    proposal = _proposal(harness)
    first_snapshot = harness.service.propose(
        harness.handler, proposal, command_id=propose_command
    )
    retry_snapshot = harness.service.propose(
        harness.handler, proposal, command_id=propose_command
    )
    assert first_snapshot == retry_snapshot
    first = first_snapshot.id

    _grant_all(harness, first, _lifecycle_envelope("start"))
    start_command = uuid.uuid4()
    lease_until = _utc_now() + timedelta(seconds=60)
    first_start = harness.service.start(
        harness.handler,
        interaction_id=first,
        lease_until=lease_until,
        command_id=start_command,
    )
    retry_start = harness.service.start(
        harness.handler,
        interaction_id=first,
        lease_until=lease_until,
        command_id=start_command,
    )
    assert retry_start == first_start
    assert (
        sum(
            event.event_type is InteractionEventType.STARTED
            for event in harness.service.history(first)
        )
        == 1
    )

    stop_command = uuid.uuid4()
    first_stop = harness.service.stop(
        interaction_id=first,
        participant_entity_id=harness.participant_ids[1],
        command_id=stop_command,
    )
    retry_stop = harness.service.stop(
        interaction_id=first,
        participant_entity_id=harness.participant_ids[1],
        command_id=stop_command,
    )
    assert retry_stop == first_stop
    assert (
        sum(
            event.event_type is InteractionEventType.STOPPED
            for event in harness.service.history(first)
        )
        == 1
    )
    with pytest.raises(CommandIdConflict):
        harness.service.complete(
            harness.handler, interaction_id=first, command_id=stop_command
        )


def test_concurrent_proposals_share_one_database_enforced_outcome(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    command_id = uuid.uuid4()
    proposal = _proposal(harness)
    barrier = threading.Barrier(12)

    def propose_once() -> InteractionSnapshot:
        barrier.wait()
        return harness.service.propose(
            harness.handler,
            proposal,
            command_id=command_id,
        )

    with ThreadPoolExecutor(max_workers=12) as executor:
        snapshots = tuple(executor.map(lambda _index: propose_once(), range(12)))

    assert len({snapshot.id for snapshot in snapshots}) == 1
    assert all(snapshot == snapshots[0] for snapshot in snapshots)
    with harness.session_factory() as session, session.begin():
        interaction_count = session.execute(
            text("SELECT count(*) FROM interactions")
        ).scalar_one()
        proposed_event_count = session.execute(
            text(
                """
                SELECT count(*)
                FROM interaction_events
                WHERE command_id = :command_id
                  AND event_type = 'proposed'
                """
            ),
            {"command_id": command_id},
        ).scalar_one()
    assert interaction_count == 1
    assert proposed_event_count == 1


def test_grant_expiry_uses_wall_clock_after_transaction_lock_stall(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id, _ = _propose(harness)
    _grant_all(
        harness,
        interaction_id,
        _lifecycle_envelope("start"),
        validity_seconds=1,
    )
    lock_session = harness.session_factory()
    lock_transaction = lock_session.begin()
    lock_session.execute(
        text("SELECT id FROM interactions WHERE id = :id FOR UPDATE"),
        {"id": interaction_id},
    ).scalar_one()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                harness.service.start,
                harness.handler,
                interaction_id=interaction_id,
                lease_until=_utc_now() + timedelta(seconds=30),
                command_id=uuid.uuid4(),
            )
            time.sleep(4.5)
            lock_transaction.commit()
            with pytest.raises(InteractionAuthorizationDenied) as caught:
                future.result()
    finally:
        if lock_transaction.is_active:
            lock_transaction.rollback()
        lock_session.close()
    assert caught.value.decision.reason is DenialReason.EXPIRED_AUTHORIZATION


def test_locked_authoritative_head_rejects_stale_start_and_unavailable_identity(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id, _ = _propose(harness)
    _grant_all(harness, interaction_id, _lifecycle_envelope("start"))
    with harness.session_factory() as session, session.begin():
        current_anchor = _seed_anchor(session, scene=902)
    _assert_denied(
        DenialReason.STALE_ANCHOR,
        lambda: _start(harness, interaction_id),
    )

    def unavailable(_stored: TimelineAnchor) -> TimelineAnchor:
        raise RuntimeError("expected identity unavailable")

    unavailable_service, unavailable_handler = _construct_service(
        harness.session_factory,
        expected_identity=unavailable,
    )
    _assert_denied(
        DenialReason.EVALUATION_UNAVAILABLE,
        lambda: unavailable_service.start(
            unavailable_handler,
            interaction_id=interaction_id,
            lease_until=_utc_now() + timedelta(seconds=60),
            command_id=uuid.uuid4(),
        ),
    )

    transition_proposal = _proposal(harness).model_copy(
        update={"anchor": current_anchor}
    )
    transition_interaction = harness.service.propose(
        harness.handler,
        transition_proposal,
        command_id=uuid.uuid4(),
    ).id
    _grant_all(harness, transition_interaction, _lifecycle_envelope("start"))
    _start(harness, transition_interaction)
    transition = _transition()
    _grant_all(harness, transition_interaction, transition.authorization_envelope())
    with harness.session_factory() as session, session.begin():
        _seed_anchor(session, scene=903)
    _assert_denied(
        DenialReason.STALE_ANCHOR,
        lambda: harness.service.transition(
            harness.handler,
            interaction_id=transition_interaction,
            transition=transition,
            command_id=uuid.uuid4(),
        ),
    )


def test_membership_changes_bump_revision_void_grants_and_replay_history(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id, _ = _propose(harness)
    _grant_all(harness, interaction_id, _lifecycle_envelope("start"))
    joined = harness.service.join(
        harness.handler,
        interaction_id=interaction_id,
        participant_entity_id=harness.participant_ids[2],
        command_id=uuid.uuid4(),
    )
    assert joined.revision == 2
    _assert_denied(
        DenialReason.STALE_AUTHORIZATION,
        lambda: _start(harness, interaction_id),
    )
    left = harness.service.leave(
        harness.handler,
        interaction_id=interaction_id,
        participant_entity_id=harness.participant_ids[2],
        command_id=uuid.uuid4(),
    )
    assert left.revision == 3
    _grant_all(harness, interaction_id, _lifecycle_envelope("start"))
    _start(harness, interaction_id)
    assert harness.service.replay(interaction_id) == harness.service.current_state(
        interaction_id
    )


def test_explicit_lease_and_cleanup_completion_make_recovery_idempotent(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id, _ = _propose(harness)
    _grant_all(harness, interaction_id, _lifecycle_envelope("start"))
    started = _start(harness, interaction_id, lease_seconds=0.2)
    assert started.lease_until is not None
    time.sleep(0.25)
    cleanup_calls: list[uuid.UUID] = []

    def cleanup(_session: Session, snapshot: InteractionSnapshot) -> None:
        cleanup_calls.append(snapshot.id)

    recovery_command = uuid.uuid4()
    hooks = (NamedRecoveryCleanupHook("release_executor", cleanup),)
    first = harness.service.recover(
        harness.handler,
        command_id=recovery_command,
        cleanup_hooks=hooks,
    )
    second = harness.service.recover(
        harness.handler,
        command_id=recovery_command,
        cleanup_hooks=hooks,
    )
    assert first == second == (interaction_id,)
    assert cleanup_calls == [interaction_id]
    events = harness.service.history(interaction_id)
    assert (
        sum(
            event.event_type is InteractionEventType.CLEANUP_COMPLETED
            for event in events
        )
        == 1
    )
    assert (
        sum(event.event_type is InteractionEventType.INTERRUPTED for event in events)
        == 1
    )
    assert harness.service.replay(interaction_id) == harness.service.current_state(
        interaction_id
    )


def test_concurrent_recoverers_execute_cleanup_under_one_exclusive_claim(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id, _ = _propose(harness)
    _grant_all(harness, interaction_id, _lifecycle_envelope("start"))
    _start(harness, interaction_id, lease_seconds=0.2)
    time.sleep(0.25)
    cleanup_calls: list[uuid.UUID] = []
    cleanup_lock = threading.Lock()

    def cleanup(_session: Session, snapshot: InteractionSnapshot) -> None:
        with cleanup_lock:
            cleanup_calls.append(snapshot.id)
        time.sleep(0.2)

    barrier = threading.Barrier(2)

    def recover_once() -> tuple[uuid.UUID, ...]:
        barrier.wait()
        return harness.service.recover(
            harness.handler,
            command_id=uuid.uuid4(),
            cleanup_hooks=(NamedRecoveryCleanupHook("exclusive_cleanup", cleanup),),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(lambda _index: recover_once(), range(2)))

    assert sorted(len(outcome) for outcome in outcomes) == [0, 1]
    assert cleanup_calls == [interaction_id]
    events = harness.service.history(interaction_id)
    assert (
        sum(
            event.event_type is InteractionEventType.RECOVERY_CLAIMED
            for event in events
        )
        == 1
    )
    assert (
        sum(
            event.event_type is InteractionEventType.CLEANUP_COMPLETED
            for event in events
        )
        == 1
    )
    assert (
        sum(event.event_type is InteractionEventType.INTERRUPTED for event in events)
        == 1
    )


def test_cooperative_public_api_flow_replay_equals_live_state(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id, _ = _propose(harness)
    _grant_all(harness, interaction_id, _lifecycle_envelope("start"))
    _start(harness, interaction_id)
    harness.service.touch(
        harness.handler,
        interaction_id=interaction_id,
        lease_until=_utc_now() + timedelta(seconds=90),
        command_id=uuid.uuid4(),
    )
    transition = _transition()
    _grant_all(harness, interaction_id, transition.authorization_envelope())
    harness.service.transition(
        harness.handler,
        interaction_id=interaction_id,
        transition=transition,
        command_id=uuid.uuid4(),
    )
    _grant_all(harness, interaction_id, _lifecycle_envelope("complete"))
    completed = harness.service.complete(
        harness.handler,
        interaction_id=interaction_id,
        command_id=uuid.uuid4(),
    )
    assert completed.status is InteractionStatus.COMPLETED
    assert harness.service.recover(harness.handler, command_id=uuid.uuid4()) == ()
    assert harness.service.replay(interaction_id) == harness.service.current_state(
        interaction_id
    )


def test_adversarial_public_api_flow_stops_and_replays_exactly(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id, _ = _propose(harness)
    _grant_all(harness, interaction_id, _lifecycle_envelope("start"))
    _start(harness, interaction_id)
    authorized = _transition(amount=7)
    _grant_all(harness, interaction_id, authorized.authorization_envelope())
    _assert_denied(
        DenialReason.AUTHORIZATION_TERMS_CHANGED,
        lambda: harness.service.transition(
            harness.handler,
            interaction_id=interaction_id,
            transition=_transition(amount=7000),
            command_id=uuid.uuid4(),
        ),
    )
    harness.service.transition(
        harness.handler,
        interaction_id=interaction_id,
        transition=authorized,
        command_id=uuid.uuid4(),
    )
    stop_command = uuid.uuid4()
    stopped = harness.service.stop(
        interaction_id=interaction_id,
        participant_entity_id=harness.participant_ids[0],
        command_id=stop_command,
    )
    assert stopped.status is InteractionStatus.STOPPED
    assert (
        harness.service.stop(
            interaction_id=interaction_id,
            participant_entity_id=harness.participant_ids[0],
            command_id=stop_command,
        )
        == stopped
    )
    assert harness.service.recover(harness.handler, command_id=uuid.uuid4()) == ()
    assert harness.service.replay(interaction_id) == harness.service.current_state(
        interaction_id
    )


def test_malformed_stored_authorization_and_policy_deny_typed(
    interaction_harness: _InteractionHarness,
) -> None:
    harness = interaction_harness
    interaction_id, _ = _propose(harness)
    _grant_all(harness, interaction_id, _lifecycle_envelope("start"))
    with harness.session_factory() as session, session.begin():
        session.execute(
            text(
                """
                UPDATE interaction_authorizations
                SET granted_at = :future, expires_at = :expiry
                WHERE interaction_id = :interaction_id
                  AND participant_entity_id = :participant_id
                """
            ),
            {
                "future": _utc_now() + timedelta(seconds=10),
                "expiry": _utc_now() + timedelta(seconds=20),
                "interaction_id": interaction_id,
                "participant_id": harness.participant_ids[0],
            },
        )
    _assert_denied(
        DenialReason.MALFORMED_AUTHORIZATION,
        lambda: _start(harness, interaction_id),
    )

    malformed_id, _ = _propose(harness)
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
        lambda: _start(harness, malformed_id),
    )


def test_migration_comments_columns_and_events_are_append_only(
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

    interaction_id, _ = _propose(harness)
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
