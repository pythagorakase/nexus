"""Rollback-only live coverage for sibling claim accounts."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]
from sqlalchemy import create_engine

from nexus.agents.orrery.epistemics import (
    ClaimParticipant,
    author_backstory_secret_sync,
    load_epistemics_hydration,
    mint_account_variant_async,
    mint_account_variant_sync,
    mint_claim_for_event,
    promote_claim_scope,
)
from nexus.agents.orrery.propagation import drain_claim_propagation_sync
from nexus.agents.orrery.reveal import drain_backstory_reveals_sync
from nexus.agents.orrery.substrate import (
    EventRecord,
    Slot,
    WorldState,
    heard_secondhand,
    knows_claim_about,
    knows_recent_event,
)
from nexus.api.slot_utils import get_slot_db_url
from tests.test_orrery.test_claim_propagation_live import (
    LIVE_SLOT,
    _insert_character,
    _insert_chunk,
    _insert_relationship,
    _install_valence_shadow,
    _settings,
)


pytestmark = pytest.mark.requires_postgres
MIGRATION_SQL = Path("migrations/090_claim_accounts.sql").read_text()
BACKSTORY_MIGRATION_SQL = Path("migrations/091_backstory_secrets.sql").read_text()
DISTORTION_MIGRATION_SQL = Path("migrations/092_claim_distortion_depth.sql").read_text()
EPISTEMICS = {
    "enabled": True,
    "claim_event_types": ["threat_issued"],
    "aware_roles": ["actor"],
}


def _install_account_shadow(cur: Any) -> None:
    """Install pre-090 projection tables, then migrate only this test schema."""

    cur.execute(
        """
        CREATE TABLE claims (
            id bigserial PRIMARY KEY,
            world_event_id bigint NOT NULL,
            summary text NOT NULL,
            scope text NOT NULL CHECK (
                scope IN ('common', 'bounded', 'private')
            ),
            source_chunk_id bigint,
            source_resolution_id bigint,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX ux_claims_world_event_v1
            ON claims (world_event_id)
            WHERE world_event_id IS NOT NULL;
        CREATE TABLE claim_awareness (
            id bigserial PRIMARY KEY,
            claim_id bigint NOT NULL,
            knower_entity_id bigint NOT NULL,
            source_tier text NOT NULL CHECK (
                source_tier IN ('participant', 'witness', 'told', 'granted')
            ),
            immediate_source_entity_id bigint,
            root_source_entity_id bigint,
            channel text,
            acquired_at_world_time timestamptz,
            source_chunk_id bigint,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (claim_id, knower_entity_id)
        );
        """
    )
    cur.execute(MIGRATION_SQL)
    cur.execute(BACKSTORY_MIGRATION_SQL)
    cur.execute(DISTORTION_MIGRATION_SQL)


@pytest.fixture()
def account_connection() -> Iterator[Any]:
    """Expose one slot-5 transaction with schema-local migrated claim tables."""

    engine = create_engine(get_slot_db_url(slot=LIVE_SLOT))
    connection = engine.connect()
    transaction = connection.begin()
    try:
        raw_connection = connection.connection.driver_connection
        with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT EXISTS (
                           SELECT 1 FROM event_types
                           WHERE type = 'claim_propagated'
                       ) AS registered,
                       EXISTS (
                           SELECT 1
                           FROM information_schema.columns
                           WHERE table_schema = ANY(current_schemas(false))
                             AND table_name = 'world_events'
                             AND column_name = 'world_time'
                       ) AS shaped
                """
            )
            migration_state = cur.fetchone()
            if not migration_state["registered"] or not migration_state["shaped"]:
                pytest.skip("slot 5 requires migration 083 for account propagation")
            schema = f"claim_accounts_{uuid4().hex[:12]}"
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            _install_account_shadow(cur)
            _install_valence_shadow(cur)
        yield connection
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def _mint_sibling_incident(
    cur: Any,
    *,
    label: str,
    scope: str = "bounded",
) -> tuple[int, int, int, int, int, int]:
    """Mint one real event with canonical and variant account rows."""

    actor, _actor_character = _insert_character(cur, f"{label}-actor")
    target, _target_character = _insert_character(cur, f"{label}-target")
    anchor, _world_time = _insert_chunk(cur)
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id,
            world_layer, source, changed_fields, payload
        ) VALUES (
            'threat_issued', %s, %s, %s, 'primary',
            'resolver', '{}', '{}'::jsonb
        ) RETURNING id
        """,
        (anchor, actor, target),
    )
    event_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO world_event_entities (event_id, role, entity_id)
        VALUES (%s, 'actor', %s), (%s, 'target', %s)
        """,
        (event_id, actor, event_id, target),
    )
    canonical = mint_claim_for_event(
        cur,
        world_event_id=event_id,
        event_type="threat_issued",
        summary=f"Canonical account for {label}.",
        participants=(
            ClaimParticipant(actor, "actor", f"{label} actor"),
            ClaimParticipant(target, "target", f"{label} target"),
        ),
        source_chunk_id=anchor,
        source_resolution_id=None,
        settings=EPISTEMICS,
    )
    assert canonical is not None
    if scope != "bounded":
        cur.execute(
            "UPDATE claims SET scope = %s WHERE id = %s",
            (scope, canonical.claim_id),
        )
    variant_id = mint_account_variant_sync(
        cur,
        source_claim_id=canonical.claim_id,
        account_label=f"{label}-variant",
        summary=f"Variant account for {label}.",
        source_chunk_id=anchor,
    )
    return event_id, anchor, actor, target, canonical.claim_id, variant_id


def test_scope_promotion_updates_every_sibling_and_hydrates_cleanly(
    account_connection: Any,
) -> None:
    """Scope promotion is one locked incident mutation, not a claim mutation."""

    raw_connection = account_connection.connection.driver_connection
    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        event_id, anchor, actor, target, canonical_id, _variant_id = (
            _mint_sibling_incident(cur, label="scope-promotion", scope="common")
        )
        promote_claim_scope(cur, claim_id=canonical_id, new_scope="bounded")
        cur.execute(
            "SELECT scope FROM claims WHERE world_event_id = %s ORDER BY id",
            (event_id,),
        )
        assert [row["scope"] for row in cur.fetchall()] == ["bounded", "bounded"]

    hydration = load_epistemics_hydration(
        account_connection,
        entity_ids=(actor, target),
        recent_event_ids=(event_id,),
        anchor_chunk_id=anchor,
    )
    assert hydration.claimed_event_scopes == {event_id: "bounded"}


def test_old_divergent_sibling_scopes_raise_during_hydration(
    account_connection: Any,
) -> None:
    """A divergent incident cannot hide after it leaves the recent window."""

    raw_connection = account_connection.connection.driver_connection
    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        event_id, anchor, actor, target, _canonical_id, variant_id = (
            _mint_sibling_incident(cur, label="old-divergent")
        )
        cur.execute(
            "UPDATE claims SET scope = 'private' WHERE id = %s",
            (variant_id,),
        )

    with pytest.raises(ValueError, match="Sibling claims.*divergent scopes"):
        load_epistemics_hydration(
            account_connection,
            entity_ids=(actor, target),
            recent_event_ids=(),
            anchor_chunk_id=anchor,
        )


def test_latent_sibling_secret_stays_private_until_its_own_gate_fires(
    account_connection: Any,
) -> None:
    """One reveal cannot promote or spread a differently gated sibling."""

    raw_connection = account_connection.connection.driver_connection
    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        event_id, anchor, actor, target, secret_a_claim, secret_b_claim = (
            _mint_sibling_incident(
                cur,
                label="latent-sibling",
                scope="private",
            )
        )
        secret_a = author_backstory_secret_sync(
            cur,
            claim_id=secret_a_claim,
            gate_template_id="holder_death",
            holder_entity_id=actor,
            source_chunk_id=anchor,
        )
        secret_b = author_backstory_secret_sync(
            cur,
            claim_id=secret_b_claim,
            gate_template_id="holder_death",
            holder_entity_id=target,
            source_chunk_id=anchor,
        )
        first_tick, first_world_time = _insert_chunk(
            cur,
            time_delta=timedelta(hours=1),
        )
        first = drain_backstory_reveals_sync(
            cur,
            tick_chunk_id=first_tick,
            settings={"enabled": True},
            state=WorldState(
                is_active={actor: False, target: True},
                world_time=first_world_time,
            ),
        )
        assert first.secret_ids == (secret_a,)
        cur.execute(
            "SELECT id, scope FROM claims WHERE world_event_id = %s ORDER BY id",
            (event_id,),
        )
        assert {row["id"]: row["scope"] for row in cur.fetchall()} == {
            secret_a_claim: "bounded",
            secret_b_claim: "private",
        }
        cur.execute(
            """
            SELECT knower_entity_id, source_tier
            FROM claim_awareness
            WHERE claim_id = %s
            ORDER BY id
            """,
            (secret_b_claim,),
        )
        assert cur.fetchall() == [
            {"knower_entity_id": target, "source_tier": "granted"}
        ]

    hydration = load_epistemics_hydration(
        account_connection,
        entity_ids=(actor, target),
        recent_event_ids=(event_id,),
        anchor_chunk_id=first_tick,
    )
    assert hydration.claimed_event_scopes == {event_id: "bounded"}

    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        second_tick, second_world_time = _insert_chunk(
            cur,
            time_delta=timedelta(hours=1),
        )
        second = drain_backstory_reveals_sync(
            cur,
            tick_chunk_id=second_tick,
            settings={"enabled": True},
            state=WorldState(
                is_active={actor: False, target: False},
                world_time=second_world_time,
            ),
        )
        assert second.secret_ids == (secret_b,)
        cur.execute(
            "SELECT scope FROM claims WHERE world_event_id = %s ORDER BY id",
            (event_id,),
        )
        assert [row["scope"] for row in cur.fetchall()] == ["bounded", "bounded"]

    converged = load_epistemics_hydration(
        account_connection,
        entity_ids=(actor, target),
        recent_event_ids=(event_id,),
        anchor_chunk_id=second_tick,
    )
    assert converged.claimed_event_scopes == {event_id: "bounded"}


def test_sync_variant_rejects_cross_incident_lineage_parent(
    account_connection: Any,
) -> None:
    """The sync writer rejects missing and cross-incident lineage parents."""

    raw_connection = account_connection.connection.driver_connection
    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        _event_a, anchor, _actor, _target, source_id, _variant_a = (
            _mint_sibling_incident(cur, label="lineage-source")
        )
        _event_b, _anchor, _actor, _target, foreign_id, _variant_b = (
            _mint_sibling_incident(cur, label="lineage-foreign")
        )
        with pytest.raises(ValueError, match="belongs to world event"):
            mint_account_variant_sync(
                cur,
                source_claim_id=source_id,
                account_label="cross-incident-parent",
                summary="This lineage must be rejected.",
                source_chunk_id=anchor,
                distorted_from_claim_id=foreign_id,
            )
        with pytest.raises(ValueError, match="Lineage parent claim 999999"):
            mint_account_variant_sync(
                cur,
                source_claim_id=source_id,
                account_label="missing-parent",
                summary="This lineage must also be rejected.",
                source_chunk_id=anchor,
                distorted_from_claim_id=999999,
            )


def test_sibling_accounts_hydrate_predicates_and_propagate_independently(
    account_connection: Any,
) -> None:
    """Specific accounts stay disjoint while incident visibility stays shared."""

    raw_connection = account_connection.connection.driver_connection
    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        canonical_knower, canonical_character = _insert_character(
            cur, "account-canonical-knower"
        )
        variant_knower, variant_character = _insert_character(
            cur, "account-variant-knower"
        )
        canonical_listener, canonical_listener_character = _insert_character(
            cur, "account-canonical-listener"
        )
        variant_listener, variant_listener_character = _insert_character(
            cur, "account-variant-listener"
        )
        subject, _subject_character = _insert_character(cur, "account-subject")
        outsider, _outsider_character = _insert_character(cur, "account-outsider")
        _insert_relationship(cur, canonical_character, canonical_listener_character)
        _insert_relationship(cur, variant_character, variant_listener_character)
        birth_chunk, birth_world_time = _insert_chunk(cur)
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, actor_entity_id, target_entity_id,
                world_layer, source, changed_fields, payload
            ) VALUES (
                'threat_issued', %s, %s, %s, 'primary',
                'resolver', '{}', '{}'::jsonb
            ) RETURNING id
            """,
            (birth_chunk, canonical_knower, subject),
        )
        event_id = int(cur.fetchone()["id"])
        cur.execute(
            """
            INSERT INTO world_event_entities (event_id, role, entity_id)
            VALUES (%s, 'actor', %s), (%s, 'target', %s)
            """,
            (event_id, canonical_knower, event_id, subject),
        )
        canonical = mint_claim_for_event(
            cur,
            world_event_id=event_id,
            event_type="threat_issued",
            summary="The canonical witness saw the threat.",
            participants=(
                ClaimParticipant(canonical_knower, "actor", "Canonical witness"),
                ClaimParticipant(subject, "target", "Threatened subject"),
            ),
            source_chunk_id=birth_chunk,
            source_resolution_id=None,
            settings=EPISTEMICS,
        )
        assert canonical is not None
        variant_id = mint_account_variant_sync(
            cur,
            source_claim_id=canonical.claim_id,
            account_label="mistaken-identity",
            summary="A second witness says someone else made the threat.",
            account_payload={"truth_marker": False, "speaker": "unknown"},
            source_chunk_id=birth_chunk,
        )
        cur.execute(
            """
            INSERT INTO claim_awareness (
                claim_id, knower_entity_id, source_tier,
                immediate_source_entity_id, root_source_entity_id, channel,
                acquired_at_world_time, source_chunk_id
            ) VALUES (%s, %s, 'told', %s, %s, 'testimony', %s, %s)
            """,
            (
                variant_id,
                variant_knower,
                canonical_knower,
                canonical_knower,
                birth_world_time,
                birth_chunk,
            ),
        )

    entities = (
        canonical_knower,
        variant_knower,
        canonical_listener,
        variant_listener,
        subject,
        outsider,
    )
    hydration = load_epistemics_hydration(
        account_connection,
        entity_ids=entities,
        recent_event_ids=(event_id,),
        anchor_chunk_id=birth_chunk,
    )
    possessed = {
        entity_id: {record.claim_id for record in records}
        for entity_id, records in (
            hydration.possessed_claim_knowledge_by_entity.items()
        )
    }
    assert possessed[canonical_knower] == {canonical.claim_id}
    assert possessed[variant_knower] == {variant_id}
    assert variant_id not in possessed[canonical_knower]
    assert canonical.claim_id not in possessed[variant_knower]
    assert hydration.claimed_event_scopes == {event_id: "bounded"}
    assert hydration.awareness_by_entity[canonical_knower] == frozenset({event_id})
    assert hydration.awareness_by_entity[variant_knower] == frozenset({event_id})

    state = WorldState(
        recent_events=(
            EventRecord(
                "threat_issued",
                tick=1,
                event_id=event_id,
                actor_entity_id=canonical_knower,
                target_entity_id=subject,
            ),
        ),
        claimed_event_scopes=hydration.claimed_event_scopes,
        awareness_by_entity=hydration.awareness_by_entity,
        claim_knowledge_by_entity=hydration.claim_knowledge_by_entity,
        common_claim_knowledge=hydration.common_claim_knowledge,
        possessed_claim_knowledge_by_entity=(
            hydration.possessed_claim_knowledge_by_entity
        ),
        epistemics_enabled=True,
        current_tick=1,
    )
    canonical_bindings = {Slot.ACTOR: canonical_knower, Slot.TARGET: subject}
    variant_bindings = {Slot.ACTOR: variant_knower, Slot.TARGET: subject}
    outsider_bindings = {Slot.ACTOR: outsider, Slot.TARGET: subject}
    assert knows_claim_about()(state, canonical_bindings)
    assert knows_claim_about()(state, variant_bindings)
    assert not knows_claim_about()(state, outsider_bindings)
    assert not heard_secondhand()(state, canonical_bindings)
    assert heard_secondhand()(state, variant_bindings)
    predicate = knows_recent_event(
        "threat_issued", within_ticks=1, target_slot=Slot.TARGET
    )
    assert predicate(state, canonical_bindings)
    assert predicate(state, variant_bindings)
    assert not predicate(state, outsider_bindings)

    with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=4))
        drained = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=_settings()
        )
        cur.execute(
            """
            SELECT claim_id, array_agg(knower_entity_id ORDER BY knower_entity_id)
                       AS knowers
            FROM claim_awareness
            WHERE claim_id IN (%s, %s)
            GROUP BY claim_id
            ORDER BY claim_id
            """,
            (canonical.claim_id, variant_id),
        )
        awareness = {int(row["claim_id"]): row["knowers"] for row in cur}
        cur.execute(
            """
            SELECT (payload ->> 'claim_id')::bigint AS claim_id, count(*) AS n
            FROM world_events
            WHERE event_type = 'claim_propagated'
              AND (payload ->> 'claim_id')::bigint IN (%s, %s)
            GROUP BY (payload ->> 'claim_id')::bigint
            """,
            (canonical.claim_id, variant_id),
        )
        ledgers = {int(row["claim_id"]): int(row["n"]) for row in cur}

    assert drained.minted_count == 2
    assert awareness[canonical.claim_id] == sorted(
        [canonical_knower, canonical_listener]
    )
    assert awareness[variant_id] == sorted([variant_knower, variant_listener])
    assert ledgers == {canonical.claim_id: 1, variant_id: 1}


@pytest.mark.asyncio
async def test_async_variant_primitive_uses_real_postgres() -> None:
    """The async twin copies anchor/scope and writes no awareness rows."""

    conn = await asyncpg.connect(get_slot_db_url(slot=LIVE_SLOT))
    transaction = conn.transaction()
    await transaction.start()
    try:
        schema = f"claim_accounts_async_{uuid4().hex[:12]}"
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET LOCAL search_path = "{schema}", public')
        await conn.execute(
            """
            CREATE TABLE claims (
                id bigserial PRIMARY KEY,
                world_event_id bigint NOT NULL,
                summary text NOT NULL,
                scope text NOT NULL CHECK (
                    scope IN ('common', 'bounded', 'private')
                ),
                source_chunk_id bigint,
                source_resolution_id bigint,
                created_at timestamptz NOT NULL DEFAULT now()
            );
            CREATE UNIQUE INDEX ux_claims_world_event_v1
                ON claims (world_event_id)
                WHERE world_event_id IS NOT NULL;
            CREATE TABLE claim_awareness (
                id bigserial PRIMARY KEY,
                claim_id bigint NOT NULL,
                knower_entity_id bigint NOT NULL
            );
            INSERT INTO claims (world_event_id, summary, scope)
            VALUES (77, 'Async canonical account.', 'private'),
                   (78, 'Foreign async canonical account.', 'private');
            """
        )
        await conn.execute(MIGRATION_SQL)
        await conn.execute(DISTORTION_MIGRATION_SQL)
        variant_id = await mint_account_variant_async(
            conn,
            source_claim_id=1,
            account_label="async-alibi",
            summary="Async sibling account.",
            account_payload={"truth_marker": False},
            source_chunk_id=None,
        )
        row = await conn.fetchrow(
            """
            SELECT world_event_id, account_label, account_payload::text AS payload,
                   scope, distorted_from_claim_id
            FROM claims WHERE id = $1
            """,
            variant_id,
        )
        awareness_count = await conn.fetchval(
            "SELECT count(*) FROM claim_awareness WHERE claim_id = $1",
            variant_id,
        )
        with pytest.raises(ValueError, match="belongs to world event"):
            await mint_account_variant_async(
                conn,
                source_claim_id=1,
                account_label="async-cross-incident",
                summary="This async lineage must be rejected.",
                source_chunk_id=None,
                distorted_from_claim_id=2,
            )
        with pytest.raises(ValueError, match="Lineage parent claim 999999"):
            await mint_account_variant_async(
                conn,
                source_claim_id=1,
                account_label="async-missing-parent",
                summary="This async lineage must also be rejected.",
                source_chunk_id=None,
                distorted_from_claim_id=999999,
            )
    finally:
        await transaction.rollback()
        await conn.close()

    assert row is not None
    assert row["world_event_id"] == 77
    assert row["account_label"] == "async-alibi"
    assert json.loads(row["payload"]) == {"truth_marker": False}
    assert row["scope"] == "private"
    assert row["distorted_from_claim_id"] == 1
    assert awareness_count == 0
