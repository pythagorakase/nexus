"""Rollback-only coverage for the Stage 2c propagation frontier.

Every test runs on one module-scoped disposable template clone whose story
clock is seeded first, so no owner save slot is opened. The synchronous
fixture then commits each test's starting graph: its characters through
``seed_character``, its conduits through ``seed_relationship`` (attributed to
``manual`` under migration 115), and the cellular faction and its culture
tag through ``seed_faction`` and ``seed_legacy_faction_tag`` (the culture read
still honors migration 043's deprecated ``operational_secrecy`` category, where
``cellular_clandestine`` lives). Each test's own writes
(chunks, claims, pair tags, drains) stay inside one transaction that always
rolls back, and each test reads only the graph seeded under its own key.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]
from sqlalchemy import create_engine

from nexus.agents.orrery.epistemics import (
    ClaimParticipant,
    mint_claim_for_event,
    mint_claim_for_event_async,
    record_revelation,
)
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.propagation import (
    contagion_policy_digest,
    drain_claim_propagation_async,
    drain_claim_propagation_sync,
)
from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
from nexus.agents.orrery.replay import (
    reconstruct_state_at_sync,
    verify_checkpoints_sync,
)
from nexus.agents.orrery.resolver import _load_recent_events, compose_actor_bindings
from tests.pg_fixtures import (
    asyncpg_kwargs,
    connect,
    disposable_slot_database,
    seed_character,
    seed_faction,
    seed_legacy_faction_tag,
    seed_relationship,
    seed_story_clock,
    sqlalchemy_url,
)
from tests.test_orrery.claim_accounts_test_support import (
    _SCENE_NUMBERS,
    EPISTEMICS,
    _canonical_rows,
    _insert_chunk,
    _insert_claim,
    _insert_pair_tag,
    _install_valence_shadow,
    _settings,
    install_claim_accounts_shadow_async,
    install_claim_accounts_shadow_sync,
    seed_chain,
    seed_conduit,
)


pytestmark = pytest.mark.requires_postgres

STORY_CLOCK = datetime(2100, 1, 1, tzinfo=timezone.utc)

# Each chain test's starting graph: that many characters linked in hop order
# by trusting conduits, committed once under the test's key.
CHAIN_LENGTHS = {
    "salience": 2,
    "large_skip": 4,
    "not_yet_mature": 2,
    "depth_cap": 4,
    "late_drain": 3,
    "non_primary": 2,
    "idempotent": 2,
    "resolution_free": 2,
    "replay_readmits": 3,
    "replay_reconstructs": 3,
}
# The hand-built graphs: characters by role, seeded in this order (so
# ``fanout-low`` takes a lower entity ID than ``fanout-high``), then the
# conduits between them as (teller, listener, valence).
CAST = (
    "single-source",
    "single-listener",
    "fanout-source",
    "fanout-low",
    "fanout-high",
    "fanout-slow",
    "gating-source",
    "gating-listener",
    "terminal-source",
    "terminal-knower",
    "terminal-downstream",
    "clockless-source",
    "clockless-listener",
    "cellular-listener",
    "drift-source",
    "drift-rogue",
    "old-checkpoint-source",
)
CONDUITS = (
    ("single-source", "single-listener", "+3|trusting"),
    ("fanout-source", "fanout-high", "+3|trusting"),
    ("fanout-source", "fanout-low", "+3|trusting"),
    ("fanout-source", "fanout-slow", "0|neutral"),
    ("gating-source", "gating-listener", "+3|trusting"),
    ("terminal-knower", "terminal-downstream", "+3|trusting"),
    ("clockless-source", "clockless-listener", "+3|trusting"),
)


class PropagationClone(NamedTuple):
    """The module's seeded clone and the committed rows each test names."""

    dbname: str
    clock_chunk_id: int
    async_source_entity_id: int
    async_source_character_id: int
    async_listener_entity_id: int
    async_listener_character_id: int
    chains: Mapping[str, list[int]]
    cast: Mapping[str, int]


@pytest.fixture(scope="module")
def propagation_clone() -> Iterator[PropagationClone]:
    """Seed one clone: the story clock first, then every test's starting graph.

    The async test's trusting edge, each chain, and each hand-built conduit are
    committed through ``seed_relationship`` (attributed to ``manual`` under
    migration 115) from this synchronous fixture, never inside a test's
    transaction or event loop. ``cast`` maps each role in ``CAST`` (plus
    ``cellular-faction``) to its entity ID.
    """

    with disposable_slot_database("qa885_claim_propagation") as dbname:
        clock_chunk_id = seed_story_clock(dbname, world_time=STORY_CLOCK)
        source_character, source_entity = seed_character(
            dbname, name="Propagation Async Source"
        )
        listener_character, listener_entity = seed_character(
            dbname, name="Propagation Async Listener"
        )
        seed_relationship(
            dbname,
            subject_character_id=source_character,
            object_character_id=listener_character,
            relationship_type="associate",
            emotional_valence="+3|trusting",
            dynamic="Rollback-only Stage 2c conduit.",
            recent_events="None.",
            history="Fixture.",
        )
        chains = {
            key: seed_chain(dbname, f"propagation-{key}", length)
            for key, length in CHAIN_LENGTHS.items()
        }
        cast: dict[str, int] = {}
        cast_characters: dict[str, int] = {}
        for role in CAST:
            cast_characters[role], cast[role] = seed_character(
                dbname, name=f"propagation-{role}"
            )
        for teller, listener, valence in CONDUITS:
            seed_conduit(
                dbname,
                cast_characters[teller],
                cast_characters[listener],
                valence=valence,
            )
        _, cast["cellular-faction"] = seed_faction(dbname, name="propagation-cellular")
        seed_legacy_faction_tag(
            dbname,
            faction_entity_id=cast["cellular-faction"],
            category="operational_secrecy",
            tag="cellular_clandestine",
        )
        yield PropagationClone(
            dbname=dbname,
            clock_chunk_id=clock_chunk_id,
            async_source_entity_id=source_entity,
            async_source_character_id=source_character,
            async_listener_entity_id=listener_entity,
            async_listener_character_id=listener_character,
            chains=chains,
            cast=cast,
        )


def _assert_migration_083(registered: bool, shaped: bool) -> None:
    """The clone is head-migrated, so migration 083's ledger must be present."""

    assert registered, "the clone must register claim_propagated (migration 083)"
    assert shaped, "the clone must carry world_events.world_time (migration 083)"


@pytest.fixture()
def live_conn(propagation_clone: PropagationClone) -> Iterator[Any]:
    """Open one clone transaction and roll back fixture writes."""

    with closing(connect(propagation_clone.dbname)) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                               SELECT 1 FROM event_types
                               WHERE type = 'claim_propagated'
                           ),
                           EXISTS (
                               SELECT 1 FROM information_schema.columns
                               WHERE table_schema = ANY(current_schemas(false))
                                 AND table_name = 'world_events'
                                 AND column_name = 'world_time'
                           )
                    """
                )
                registered, shaped = cur.fetchone()
                _assert_migration_083(registered, shaped)
                cur.execute("SELECT max(id) FROM narrative_chunks")
                assert (
                    cur.fetchone()[0] == propagation_clone.clock_chunk_id
                ), "the seeded story-clock chunk is the clone's head chunk"
                install_claim_accounts_shadow_sync(cur)
                _install_valence_shadow(cur)
            yield conn
        finally:
            conn.rollback()


def _awareness(cur: Any, claim_id: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, claim_id, knower_entity_id, source_tier,
               immediate_source_entity_id, root_source_entity_id, channel,
               acquired_at_world_time, source_chunk_id, created_at
        FROM claim_awareness
        WHERE claim_id = %s
        ORDER BY acquired_at_world_time, knower_entity_id
        """,
        (claim_id,),
    )
    return [dict(row) for row in cur.fetchall()]


def _propagation_events(cur: Any, claim_id: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, tick_chunk_id, actor_entity_id, target_entity_id,
               world_layer::text, source::text, changed_fields, resolution_id,
               payload, world_time
        FROM world_events
        WHERE event_type = 'claim_propagated'
          AND (payload ->> 'claim_id')::bigint = %s
        ORDER BY world_time, id
        """,
        (claim_id,),
    )
    return [dict(row) for row in cur.fetchall()]


def test_single_hop_ledgers_scheduled_time_provenance_and_policy(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """One mature edge mints matching projection and payload-only event."""

    settings = _settings()
    source = propagation_clone.cast["single-source"]
    listener = propagation_clone.cast["single-listener"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=source,
            birth_world_time=birth_world_time,
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=8))
        result = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=settings
        )
        rows = _awareness(cur, claim_id)
        events = _propagation_events(cur, claim_id)
        cur.execute("SELECT world_event_id FROM claims WHERE id = %s", (claim_id,))
        incident_world_event_id = int(cur.fetchone()["world_event_id"])
        cur.execute(
            """
            SELECT role::text, entity_id
            FROM world_event_entities
            WHERE event_id = %s
            ORDER BY role
            """,
            (events[0]["id"],),
        )
        participants = {(row["role"], int(row["entity_id"])) for row in cur}

    assert result.minted_count == 1
    told = rows[1]
    assert {
        key: told[key]
        for key in (
            "knower_entity_id",
            "source_tier",
            "immediate_source_entity_id",
            "root_source_entity_id",
            "channel",
            "acquired_at_world_time",
            "source_chunk_id",
        )
    } == {
        "knower_entity_id": listener,
        "source_tier": "told",
        "immediate_source_entity_id": source,
        "root_source_entity_id": source,
        "channel": "dyad:associate",
        "acquired_at_world_time": birth_world_time + timedelta(hours=1),
        "source_chunk_id": drain_chunk,
    }
    event = events[0]
    assert event["world_time"] == birth_world_time + timedelta(hours=1)
    assert event["tick_chunk_id"] == drain_chunk
    assert event["actor_entity_id"] is None
    assert event["target_entity_id"] is None
    assert event["source"] == "resolver"
    assert event["changed_fields"] == ["claim_awareness"]
    assert event["resolution_id"] is None
    assert event["payload"] == {
        "awareness_id": told["id"],
        "claim_id": claim_id,
        "delivered_claim_id": claim_id,
        "incident_world_event_id": incident_world_event_id,
        "distortion_applied": False,
        "knower_entity_id": listener,
        "immediate_source_entity_id": source,
        "root_source_entity_id": source,
        "channel": "dyad:associate",
        "latency_seconds": 3600.0,
        "depth": 1,
        "policy_digest": contagion_policy_digest(settings),
    }
    assert participants == set()


def test_propagation_event_does_not_change_salience_or_hydration_feed(
    propagation_clone: PropagationClone,
) -> None:
    """Payload-only acquisitions stay out of actor and recent-event readers."""

    engine = create_engine(sqlalchemy_url(propagation_clone.dbname))
    connection = engine.connect()
    transaction = connection.begin()
    try:
        raw_connection = connection.connection.driver_connection
        assert raw_connection is not None
        with raw_connection.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT EXISTS (
                           SELECT 1 FROM event_types
                           WHERE type = 'claim_propagated'
                       ) AS registered,
                       EXISTS (
                           SELECT 1 FROM information_schema.columns
                           WHERE table_schema = ANY(current_schemas(false))
                             AND table_name = 'world_events'
                             AND column_name = 'world_time'
                       ) AS shaped
                """
            )
            migration_state = cur.fetchone()
            _assert_migration_083(
                migration_state["registered"], migration_state["shaped"]
            )
            install_claim_accounts_shadow_sync(cur)
            _install_valence_shadow(cur)
            entities = propagation_clone.chains["salience"]
            birth_chunk, birth_world_time = _insert_chunk(cur)
            claim_id = _insert_claim(
                cur,
                chunk_id=birth_chunk,
                source_entity_id=entities[0],
                birth_world_time=birth_world_time,
            )
            drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=4))
            before_bindings = compose_actor_bindings(
                connection, anchor_chunk_id=drain_chunk, window_chunks=1
            )
            before_events = _load_recent_events(
                connection, anchor_chunk_id=drain_chunk, window_chunks=1
            )
            result = drain_claim_propagation_sync(
                cur, tick_chunk_id=drain_chunk, settings=_settings()
            )
            after_bindings = compose_actor_bindings(
                connection, anchor_chunk_id=drain_chunk, window_chunks=1
            )
            after_events = _load_recent_events(
                connection, anchor_chunk_id=drain_chunk, window_chunks=1
            )
            events = _propagation_events(cur, claim_id)
            cur.execute(
                "SELECT count(*) AS count FROM world_event_entities "
                "WHERE event_id = %s",
                (events[0]["id"],),
            )
            participant_count = int(cur.fetchone()["count"])

        assert result.minted_count == 1
        assert before_bindings == after_bindings
        assert before_events == after_events
        assert participant_count == 0
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def test_large_skip_drains_chained_hops_at_staggered_times(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """A single fixpoint drain releases every mature hop, never at W."""

    entities = propagation_clone.chains["large_skip"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=12))
        result = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=_settings()
        )
        rows = _awareness(cur, claim_id)
        events = _propagation_events(cur, claim_id)

    assert result.minted_count == 3
    assert [row["knower_entity_id"] for row in rows] == entities
    assert [row["acquired_at_world_time"] for row in rows] == [
        birth_world_time + timedelta(hours=offset) for offset in range(4)
    ]
    assert [event["payload"]["depth"] for event in events] == [1, 2, 3]
    assert [event["world_time"] for event in events] == [
        birth_world_time + timedelta(hours=offset) for offset in range(1, 4)
    ]


def test_not_yet_mature_edge_waits(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """An edge whose scheduled acquisition is later than W stays pending."""

    entities = propagation_clone.chains["not_yet_mature"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(minutes=59))
        result = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=_settings()
        )
        rows = _awareness(cur, claim_id)

    assert result.minted_count == 0
    assert [row["knower_entity_id"] for row in rows] == [entities[0]]


def test_fan_out_cap_uses_latency_then_listener_id(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """Only the sorted first cap edges ever transmit for a knower/claim."""

    settings = _settings(neutral="2h", fan_out_cap=2)
    source = propagation_clone.cast["fanout-source"]
    low = propagation_clone.cast["fanout-low"]
    high = propagation_clone.cast["fanout-high"]
    slow = propagation_clone.cast["fanout-slow"]
    assert low < high, "fanout-low is seeded first, so it has the lower entity ID"
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=source,
            birth_world_time=birth_world_time,
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=8))
        result = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=settings
        )
        knowers = {row["knower_entity_id"] for row in _awareness(cur, claim_id)}

    assert result.minted_count == 2
    assert knowers == {source, low, high}
    assert slow not in knowers


def test_depth_cap_is_recovered_across_separate_drains(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """Persisted event depth releases hop two later and blocks hop three."""

    settings = _settings(depth_cap=2)
    entities = propagation_clone.chains["depth_cap"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        first_chunk, first_world_time = _insert_chunk(
            cur, time_delta=timedelta(hours=1)
        )
        first = drain_claim_propagation_sync(
            cur, tick_chunk_id=first_chunk, settings=settings
        )
        second_chunk, _ = _insert_chunk(
            cur,
            time_delta=timedelta(hours=12) - (first_world_time - birth_world_time),
        )
        second = drain_claim_propagation_sync(
            cur, tick_chunk_id=second_chunk, settings=settings
        )
        rows = _awareness(cur, claim_id)
        events = _propagation_events(cur, claim_id)

    assert first.minted_count == 1
    assert second.minted_count == 1
    assert [row["knower_entity_id"] for row in rows] == entities[:3]
    assert [event["payload"]["depth"] for event in events] == [1, 2]


def test_age_horizon_and_nonbounded_scopes_do_not_propagate(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """Old bounded, private, and common claims retain only seeded awareness."""

    settings = _settings(trusting="3h", age_horizon="2h")
    source = propagation_clone.cast["gating-source"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        old_chunk, old_world_time = _insert_chunk(cur)
        old_claim = _insert_claim(
            cur,
            chunk_id=old_chunk,
            source_entity_id=source,
            birth_world_time=old_world_time,
        )
        recent_chunk, recent_world_time = _insert_chunk(
            cur, time_delta=timedelta(hours=9)
        )
        private_claim = _insert_claim(
            cur,
            chunk_id=recent_chunk,
            source_entity_id=source,
            birth_world_time=recent_world_time,
            scope="private",
        )
        common_claim = _insert_claim(
            cur,
            chunk_id=recent_chunk,
            source_entity_id=source,
            birth_world_time=recent_world_time,
            scope="common",
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=1))
        result = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=settings
        )
        counts = {
            claim_id: len(_awareness(cur, claim_id))
            for claim_id in (old_claim, private_claim, common_claim)
        }

    assert result.minted_count == 0
    assert counts == {old_claim: 1, private_claim: 1, common_claim: 1}


def test_late_drain_lands_hop_scheduled_inside_age_horizon(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """Hop eligibility uses its scheduled time, never narration cadence W."""

    entities = propagation_clone.chains["late_drain"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        first_chunk, first_world_time = _insert_chunk(
            cur, time_delta=timedelta(hours=1)
        )
        first = drain_claim_propagation_sync(
            cur, tick_chunk_id=first_chunk, settings=_settings(age_horizon="14d")
        )
        late_chunk, _ = _insert_chunk(
            cur,
            time_delta=timedelta(days=15) - (first_world_time - birth_world_time),
        )
        late = drain_claim_propagation_sync(
            cur, tick_chunk_id=late_chunk, settings=_settings(age_horizon="14d")
        )
        rows = _awareness(cur, claim_id)

    assert first.minted_count == 1
    assert late.minted_count == 1
    assert [row["knower_entity_id"] for row in rows] == entities
    assert rows[2]["acquired_at_world_time"] == birth_world_time + timedelta(hours=2)


def test_null_awareness_is_possession_terminal(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """A clockless knower blocks re-minting but schedules no outbound hop."""

    source = propagation_clone.cast["terminal-source"]
    terminal = propagation_clone.cast["terminal-knower"]
    downstream = propagation_clone.cast["terminal-downstream"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=source,
            birth_world_time=birth_world_time,
        )
        revelation = record_revelation(
            cur,
            claim_id=claim_id,
            knower_entity_id=terminal,
            source_entity_id=source,
            channel="clockless-message",
            world_time=None,
            source_chunk_id=birth_chunk,
        )
        assert revelation.inserted is True
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=8))
        result = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=_settings()
        )
        rows = _awareness(cur, claim_id)

    assert result.minted_count == 0
    by_knower = {row["knower_entity_id"]: row for row in rows}
    assert by_knower[terminal]["acquired_at_world_time"] is None
    assert downstream not in by_knower


def test_null_birth_world_time_excludes_claim_from_propagation(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """A genuinely clockless claim is legal history outside the frontier."""

    source = propagation_clone.cast["clockless-source"]
    listener = propagation_clone.cast["clockless-listener"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO narrative_chunks (raw_text, storyteller_text)
            VALUES (%s, 'Rollback-only clockless fixture.')
            RETURNING id
            """,
            (f"Stage 2c clockless birth {uuid4().hex[:12]}.",),
        )
        clockless_chunk = int(cur.fetchone()["id"])
        claim_id = _insert_claim(
            cur,
            chunk_id=clockless_chunk,
            source_entity_id=source,
            birth_world_time=None,
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=8))
        result = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=_settings()
        )
        rows = _awareness(cur, claim_id)

    assert result.minted_count == 0
    assert [row["knower_entity_id"] for row in rows] == [source]
    assert rows[0]["acquired_at_world_time"] is None
    assert listener not in {row["knower_entity_id"] for row in rows}


def test_non_primary_commit_skips_propagation_drain(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """Dream/flashback/atemporal-equivalent chunks never move knowledge."""

    entities = propagation_clone.chains["non_primary"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        dream_chunk, _ = _insert_chunk(
            cur, time_delta=timedelta(hours=8), world_layer="atemporal"
        )
        result = drain_claim_propagation_sync(
            cur, tick_chunk_id=dream_chunk, settings=_settings()
        )
        rows = _awareness(cur, claim_id)

    assert result.minted_count == 0
    assert result.policy_digest is None
    assert [row["knower_entity_id"] for row in rows] == [entities[0]]


def test_cellular_clandestine_channel_uses_multiplied_latency(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """Institutional culture delays the scheduled channel acquisition."""

    settings = _settings(
        trusting="never",
        channels={
            "authority_over": {
                "direction": "subject_to_object",
                "latency": "1h",
            }
        },
        culture_profiles={"cellular_clandestine": 4.0},
    )
    faction = propagation_clone.cast["cellular-faction"]
    listener = propagation_clone.cast["cellular-listener"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        _insert_pair_tag(cur, faction, listener, "authority_over")
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=faction,
            birth_world_time=birth_world_time,
        )
        early_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=3))
        early = drain_claim_propagation_sync(
            cur, tick_chunk_id=early_chunk, settings=settings
        )
        mature_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=5))
        mature = drain_claim_propagation_sync(
            cur, tick_chunk_id=mature_chunk, settings=settings
        )
        rows = _awareness(cur, claim_id)

    assert early.minted_count == 0
    assert mature.minted_count == 1
    assert rows[1]["channel"] == "channel:authority_over"
    assert rows[1]["acquired_at_world_time"] == birth_world_time + timedelta(hours=4)


def test_idempotent_redrain_and_disabled_config_are_noops(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """The awareness uniqueness key closes a drain; disabled reads nothing."""

    settings = _settings()
    entities = propagation_clone.chains["idempotent"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=4))
        first = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=settings
        )
        second = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=settings
        )
        disabled = drain_claim_propagation_sync(
            cur,
            tick_chunk_id=-1,
            settings=_settings(enabled=False),
        )
        events = _propagation_events(cur, claim_id)

    assert first.minted_count == 1
    assert second.minted_count == 0
    assert disabled.minted_count == 0
    assert len(events) == 1


def test_resolution_free_commit_still_drains(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """An accepted tick with no proposal/resolutions still advances knowledge."""

    entities = propagation_clone.chains["resolution_free"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=4))

    result = commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=drain_chunk,
        contagion_settings=_settings(),
    )
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        rows = _awareness(cur, claim_id)

    assert result.resolution_count == 0
    assert result.propagation_count == 1
    assert result.event_count == 0
    assert len(rows) == 2


def test_replay_readmits_target_participant_awareness_and_never_mints_beneficiary(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """PR #697 replay readmits a target but never birth-mints a beneficiary.

    ``threat_issued`` is a bounded two-party type: actor and target awareness
    reconstruct without drift, even when the event also names a beneficiary.
    """

    birth_settings = {
        **EPISTEMICS,
        "aware_roles": ["actor", "target", "beneficiary"],
    }
    entities = propagation_clone.chains["replay_readmits"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        actor_id, target_id, beneficiary_id = entities
        base_chunk, _ = _insert_chunk(cur)
        with live_conn.cursor() as checkpoint_cur:
            checkpoint_id = capture_state_checkpoint_sync(
                checkpoint_cur, chunk_id=base_chunk, label="manual"
            )
        assert checkpoint_id is not None
        mint_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=2))
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, actor_entity_id, target_entity_id,
                world_layer,
                source, changed_fields, payload
            ) VALUES (
                'threat_issued', %s, %s, %s, 'primary',
                'resolver', '{}', '{}'::jsonb
            )
            RETURNING id
            """,
            (mint_chunk, actor_id, target_id),
        )
        event_id = int(cur.fetchone()["id"])
        cur.execute(
            """
            INSERT INTO world_event_entities (event_id, role, entity_id)
            VALUES (%s, 'actor', %s), (%s, 'target', %s),
                   (%s, 'beneficiary', %s)
            """,
            (
                event_id,
                actor_id,
                event_id,
                target_id,
                event_id,
                beneficiary_id,
            ),
        )
        minted = mint_claim_for_event(
            cur,
            world_event_id=event_id,
            event_type="threat_issued",
            summary="Rollback-only target and beneficiary claim.",
            participants=(
                ClaimParticipant(actor_id, "actor", "Actor", "character"),
                ClaimParticipant(target_id, "target", "Target", "character"),
                ClaimParticipant(
                    beneficiary_id, "beneficiary", "Beneficiary", "character"
                ),
            ),
            source_chunk_id=mint_chunk,
            source_resolution_id=None,
            settings=birth_settings,
        )
        assert minted is not None
        live_rows = _awareness(cur, minted.claim_id)
        assert {int(r["knower_entity_id"]) for r in live_rows} == {
            actor_id,
            target_id,
        }
        with live_conn.cursor() as replay_cur:
            replay = reconstruct_state_at_sync(
                replay_cur, mint_chunk, base_checkpoint_id=checkpoint_id
            )

    replayed_rows = [
        row
        for row in replay.state["claim_awareness"]
        if row["claim_id"] == minted.claim_id
    ]
    replayed_knowers = {int(row["knower_entity_id"]) for row in replayed_rows}
    assert target_id in replayed_knowers
    assert beneficiary_id not in replayed_knowers
    assert _canonical_rows(replayed_rows) == _canonical_rows(live_rows)


def test_replay_reconstructs_propagated_awareness_from_event(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """The event ledger reproduces the live awareness projection after a drain."""

    entities = propagation_clone.chains["replay_reconstructs"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        birth_chunk, birth_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=birth_chunk,
            source_entity_id=entities[0],
            birth_world_time=birth_world_time,
        )
        with live_conn.cursor() as checkpoint_cur:
            checkpoint_id = capture_state_checkpoint_sync(
                checkpoint_cur, chunk_id=birth_chunk, label="manual"
            )
        assert checkpoint_id is not None
        drain_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=8))
        drained = drain_claim_propagation_sync(
            cur, tick_chunk_id=drain_chunk, settings=_settings()
        )
        live_rows = _awareness(cur, claim_id)
        with live_conn.cursor() as replay_cur:
            replay = reconstruct_state_at_sync(
                replay_cur, drain_chunk, base_checkpoint_id=checkpoint_id
            )

    replayed_rows = [
        row for row in replay.state["claim_awareness"] if row["claim_id"] == claim_id
    ]
    assert drained.minted_count == 2
    assert _canonical_rows(replayed_rows) == _canonical_rows(live_rows)


def test_checkpoint_verify_reports_unledgered_awareness_drift(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """A projection-only awareness INSERT is visible to the replay oracle."""

    source = propagation_clone.cast["drift-source"]
    rogue = propagation_clone.cast["drift-rogue"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        base_chunk, base_world_time = _insert_chunk(cur)
        claim_id = _insert_claim(
            cur,
            chunk_id=base_chunk,
            source_entity_id=source,
            birth_world_time=base_world_time,
        )
        with live_conn.cursor() as checkpoint_cur:
            base_checkpoint_id = capture_state_checkpoint_sync(
                checkpoint_cur, chunk_id=base_chunk, label="manual"
            )
        assert base_checkpoint_id is not None

        target_chunk, target_world_time = _insert_chunk(
            cur, time_delta=timedelta(hours=1)
        )
        cur.execute(
            """
            INSERT INTO claim_awareness (
                claim_id, knower_entity_id, source_tier,
                acquired_at_world_time, source_chunk_id
            ) VALUES (%s, %s, 'participant', %s, %s)
            RETURNING id
            """,
            (claim_id, rogue, target_world_time, target_chunk),
        )
        rogue_awareness_id = int(cur.fetchone()["id"])
        with live_conn.cursor() as checkpoint_cur:
            target_checkpoint_id = capture_state_checkpoint_sync(
                checkpoint_cur, chunk_id=target_chunk, label="manual"
            )
        assert target_checkpoint_id is not None
        with live_conn.cursor() as verify_cur:
            verdicts = verify_checkpoints_sync(verify_cur)

    verdict = next(
        item
        for item in verdicts
        if item.base_checkpoint_id == base_checkpoint_id
        and item.target_checkpoint_id == target_checkpoint_id
    )
    assert any(
        drift.section == "claim_awareness"
        and drift.row_key == str(rogue_awareness_id)
        and drift.kind == "missing_row"
        for drift in verdict.drifts
    )


def test_old_checkpoint_without_awareness_section_is_skipped(
    live_conn: Any, propagation_clone: PropagationClone
) -> None:
    """Pre-section checkpoints remain verifiable through explicit skipping."""

    source = propagation_clone.cast["old-checkpoint-source"]
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        base_chunk, base_world_time = _insert_chunk(cur)
        _insert_claim(
            cur,
            chunk_id=base_chunk,
            source_entity_id=source,
            birth_world_time=base_world_time,
        )
        with live_conn.cursor() as checkpoint_cur:
            base_checkpoint_id = capture_state_checkpoint_sync(
                checkpoint_cur, chunk_id=base_chunk, label="manual"
            )
        assert base_checkpoint_id is not None
        cur.execute(
            """
            UPDATE state_checkpoints
            SET state = state - 'claim_awareness'
            WHERE id = %s
            """,
            (base_checkpoint_id,),
        )
        target_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=1))
        with live_conn.cursor() as checkpoint_cur:
            target_checkpoint_id = capture_state_checkpoint_sync(
                checkpoint_cur, chunk_id=target_chunk, label="manual"
            )
        assert target_checkpoint_id is not None
        with live_conn.cursor() as verify_cur:
            verdicts = verify_checkpoints_sync(verify_cur)

    verdict = next(
        item
        for item in verdicts
        if item.base_checkpoint_id == base_checkpoint_id
        and item.target_checkpoint_id == target_checkpoint_id
    )
    assert not [drift for drift in verdict.drifts if drift.section == "claim_awareness"]
    assert verdict.skipped_unreproducible >= 1
    assert any(
        "comparison skipped" in note
        for note in verdict.notes.get("claim_awareness", [])
    )


@pytest.mark.asyncio
async def test_async_drain_matches_sync_single_hop(
    propagation_clone: PropagationClone,
) -> None:
    """The async accepted-chunk twin mints the same scheduled ledger pair."""

    source = propagation_clone.async_source_entity_id
    listener = propagation_clone.async_listener_entity_id
    conn = await asyncpg.connect(**asyncpg_kwargs(propagation_clone.dbname))
    transaction = conn.transaction()
    await transaction.start()
    try:
        migration_state = await conn.fetchrow(
            """
            SELECT EXISTS (
                       SELECT 1 FROM event_types
                       WHERE type = 'claim_propagated'
                   ) AS registered,
                   EXISTS (
                       SELECT 1 FROM information_schema.columns
                       WHERE table_schema = ANY(current_schemas(false))
                         AND table_name = 'world_events'
                         AND column_name = 'world_time'
                   ) AS shaped
            """
        )
        _assert_migration_083(migration_state["registered"], migration_state["shaped"])
        await install_claim_accounts_shadow_async(conn)
        await conn.execute(
            r"""
            CREATE TEMP TABLE character_relationships ON COMMIT DROP AS
            SELECT cr.* FROM public.character_relationships cr;

            ALTER TABLE pg_temp.character_relationships
                ADD COLUMN IF NOT EXISTS valence_current numeric;

            UPDATE pg_temp.character_relationships
            SET valence_current = substring(
                emotional_valence::text FROM '^([+-]?[0-9]+)\|'
            )::numeric / 5.5
            WHERE valence_current IS NULL
            """
        )
        # The seeded, producer-attributed conduit reaches the drain through
        # the valence shadow with the trusting tier's valence.
        conduit = await conn.fetchrow(
            """
            SELECT relationship_type, emotional_valence, valence_current
            FROM pg_temp.character_relationships
            WHERE character1_id = $1 AND character2_id = $2
            """,
            propagation_clone.async_source_character_id,
            propagation_clone.async_listener_character_id,
        )
        assert conduit is not None
        assert conduit["relationship_type"] == "associate"
        assert conduit["emotional_valence"] == "+3|trusting"
        assert float(conduit["valence_current"]) == pytest.approx(3 / 5.5)
        birth_chunk, birth_world_time = await _insert_chunk_async(conn)
        event_id = int(
            await conn.fetchval(
                """
                INSERT INTO world_events (
                    event_type, tick_chunk_id, actor_entity_id, world_layer,
                    source, changed_fields, payload
                ) VALUES (
                    'threat_issued', $1, $2, 'primary',
                    'resolver', '{}', '{}'::jsonb
                ) RETURNING id
                """,
                birth_chunk,
                source,
            )
        )
        await conn.execute(
            """
            INSERT INTO world_event_entities (event_id, role, entity_id)
            VALUES ($1, 'actor', $2)
            """,
            event_id,
            source,
        )
        minted = await mint_claim_for_event_async(
            conn,
            world_event_id=event_id,
            event_type="threat_issued",
            summary="Async propagated claim.",
            participants=(
                ClaimParticipant(
                    source,
                    "actor",
                    f"Async propagation source {source}",
                    "character",
                ),
            ),
            source_chunk_id=birth_chunk,
            source_resolution_id=None,
            settings=EPISTEMICS,
        )
        assert minted is not None
        claim_id = minted.claim_id
        drain_chunk, _ = await _insert_chunk_async(conn, time_delta=timedelta(hours=8))
        result = await drain_claim_propagation_async(
            conn,
            tick_chunk_id=drain_chunk,
            settings=_settings(),
        )
        awareness = await conn.fetchrow(
            """
            SELECT immediate_source_entity_id, root_source_entity_id,
                   acquired_at_world_time, source_chunk_id
            FROM claim_awareness
            WHERE claim_id = $1 AND knower_entity_id = $2
            """,
            claim_id,
            listener,
        )
        ledger_time = await conn.fetchval(
            """
            SELECT world_time FROM world_events
            WHERE event_type = 'claim_propagated'
              AND (payload ->> 'claim_id')::bigint = $1
            """,
            claim_id,
        )
    finally:
        await transaction.rollback()
        await conn.close()

    assert result.minted_count == 1
    assert awareness is not None
    assert awareness["immediate_source_entity_id"] == source
    assert awareness["root_source_entity_id"] == source
    expected_acquisition = birth_world_time + timedelta(hours=1)
    assert awareness["acquired_at_world_time"] == expected_acquisition
    assert awareness["source_chunk_id"] == drain_chunk
    assert ledger_time == expected_acquisition


async def _insert_chunk_async(
    conn: Any,
    *,
    time_delta: timedelta = timedelta(0),
    world_layer: str = "primary",
) -> tuple[int, datetime]:
    token = uuid4().hex[:12]
    chunk_id = int(
        await conn.fetchval(
            "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
            "VALUES ($1, 'Rollback-only async fixture.') RETURNING id",
            f"Stage 2c async chunk {token}.",
        )
    )
    await conn.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, time_delta,
            generation_date, slug
        ) VALUES (
            $1, 99, 99, $2, $3::world_layer_type, $4, now(), $5
        )
        """,
        chunk_id,
        next(_SCENE_NUMBERS),
        world_layer,
        time_delta,
        token[:10],
    )
    stamped = await conn.fetchval(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = $1", chunk_id
    )
    assert stamped is not None
    return chunk_id, stamped
