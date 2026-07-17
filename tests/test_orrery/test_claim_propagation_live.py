"""Rollback-only slot-5 coverage for the Stage 2c propagation frontier."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterator, Mapping, Sequence
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import psycopg2  # type: ignore[import-untyped]
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
    canonicalize,
    reconstruct_state_at_sync,
    verify_checkpoints_sync,
)
from nexus.agents.orrery.resolver import _load_recent_events, compose_actor_bindings
from nexus.api.slot_utils import get_slot_db_url
from nexus.config.settings_models import OrreryContagionSettings


pytestmark = pytest.mark.requires_postgres

LIVE_SLOT = 5
EPISTEMICS = {
    "enabled": True,
    "claim_event_types": ["threat_issued"],
    "aware_roles": ["actor", "target", "observer", "witness"],
}


@pytest.fixture()
def live_conn() -> Iterator[Any]:
    """Open one slot-5 transaction and roll back fixture writes."""

    conn = psycopg2.connect(get_slot_db_url(slot=LIVE_SLOT))
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
            if not registered or not shaped:
                pytest.skip(
                    "slot 5 has not applied migration 083: claim_propagated "
                    "registration and world_events.world_time are required"
                )
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _settings(
    *,
    trusting: str = "1h",
    neutral: str = "never",
    hostile: str = "never",
    depth_cap: int = 4,
    age_horizon: str = "14d",
    fan_out_cap: int = 6,
    channels: Mapping[str, Any] | None = None,
    culture_profiles: Mapping[str, float] | None = None,
    enabled: bool = True,
) -> OrreryContagionSettings:
    return OrreryContagionSettings.model_validate(
        {
            "enabled": enabled,
            "dyad_tiers": {
                "trusting": trusting,
                "neutral": neutral,
                "hostile": hostile,
            },
            "dyad_overrides": {},
            "channels": dict(channels or {}),
            "culture_profiles": dict(culture_profiles or {}),
            "guards": {
                "depth_cap": depth_cap,
                "age_horizon": age_horizon,
                "fan_out_cap": fan_out_cap,
            },
        }
    )


def _insert_chunk(
    cur: Any,
    *,
    time_delta: timedelta = timedelta(0),
    world_layer: str = "primary",
) -> tuple[int, datetime]:
    token = uuid4().hex[:12]
    cur.execute(
        """
        INSERT INTO narrative_chunks (raw_text, storyteller_text)
        VALUES (%s, 'Rollback-only Stage 2c fixture.')
        RETURNING id
        """,
        (f"Stage 2c propagation fixture {token}.",),
    )
    chunk_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, time_delta,
            generation_date, slug
        ) VALUES (
            %s, 99, 99, %s, %s::world_layer_type, %s, now(), %s
        )
        """,
        (chunk_id, chunk_id, world_layer, time_delta, token[:10]),
    )
    cur.execute(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s", (chunk_id,)
    )
    stamped_world_time = cur.fetchone()["world_time"]
    assert stamped_world_time is not None
    return chunk_id, stamped_world_time


def _insert_character(cur: Any, label: str) -> tuple[int, int]:
    token = uuid4().hex[:10]
    cur.execute(
        "INSERT INTO entities (kind, is_active) "
        "VALUES ('character', true) RETURNING id"
    )
    entity_id = int(cur.fetchone()["id"])
    cur.execute(
        "INSERT INTO characters (name, entity_id) VALUES (%s, %s) RETURNING id",
        (f"propagation-{label}-{token}", entity_id),
    )
    return entity_id, int(cur.fetchone()["id"])


def _insert_faction(cur: Any, label: str) -> int:
    cur.execute(
        "INSERT INTO entities (kind, is_active) "
        "VALUES ('faction', true) RETURNING id"
    )
    entity_id = int(cur.fetchone()["id"])
    cur.execute("SELECT coalesce(max(id), 0) + 1 AS id FROM factions")
    faction_id = int(cur.fetchone()["id"])
    cur.execute(
        "INSERT INTO factions (id, name, entity_id) VALUES (%s, %s, %s)",
        (faction_id, f"propagation-{label}-{uuid4().hex[:10]}", entity_id),
    )
    return entity_id


def _insert_relationship(
    cur: Any,
    source_character_id: int,
    target_character_id: int,
    *,
    valence: str = "+3|trusting",
) -> None:
    cur.execute(
        """
        INSERT INTO character_relationships (
            character1_id, character2_id, relationship_type,
            emotional_valence, dynamic, recent_events, history
        ) VALUES (
            %s, %s, 'associate', %s,
            'Rollback-only Stage 2c conduit.', 'None.', 'Fixture.'
        )
        """,
        (source_character_id, target_character_id, valence),
    )


def _insert_pair_tag(
    cur: Any, subject_entity_id: int, object_entity_id: int, tag: str
) -> None:
    cur.execute(
        """
        INSERT INTO entity_pair_tags (
            subject_entity_id, object_entity_id, pair_tag_id,
            source_kind, template_id
        )
        SELECT %s, %s, id, 'template', 'test_claim_propagation_live'
        FROM pair_tags WHERE tag = %s AND NOT deprecated
        """,
        (subject_entity_id, object_entity_id, tag),
    )
    assert cur.rowcount == 1


def _insert_culture_tag(cur: Any, entity_id: int, tag: str) -> None:
    cur.execute(
        """
        INSERT INTO entity_tags (entity_id, tag_id, source_kind, template_id)
        SELECT %s, id, 'template', 'test_claim_propagation_live'
        FROM tags WHERE tag = %s AND NOT deprecated
        """,
        (entity_id, tag),
    )
    assert cur.rowcount == 1


def _insert_claim(
    cur: Any,
    *,
    chunk_id: int,
    source_entity_id: int,
    birth_world_time: datetime | None,
    scope: str = "bounded",
) -> int:
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, world_layer,
            source, changed_fields, payload
        ) VALUES (
            'threat_issued', %s, %s, 'primary', 'resolver', '{}', '{}'::jsonb
        )
        RETURNING id
        """,
        (chunk_id, source_entity_id),
    )
    event_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO world_event_entities (event_id, role, entity_id)
        VALUES (%s, 'actor', %s)
        """,
        (event_id, source_entity_id),
    )
    cur.execute("SELECT kind::text FROM entities WHERE id = %s", (source_entity_id,))
    source_kind = str(cur.fetchone()["kind"])
    minted = mint_claim_for_event(
        cur,
        world_event_id=event_id,
        event_type="threat_issued",
        summary="Rollback-only propagated claim.",
        participants=(
            ClaimParticipant(
                source_entity_id,
                "actor",
                f"Propagation source {source_entity_id}",
                source_kind,
            ),
        ),
        source_chunk_id=chunk_id,
        source_resolution_id=None,
        settings=EPISTEMICS,
    )
    assert minted is not None
    claim_id = minted.claim_id
    if scope != "bounded":
        cur.execute("UPDATE claims SET scope = %s WHERE id = %s", (scope, claim_id))
    cur.execute(
        """
        SELECT acquired_at_world_time
        FROM claim_awareness
        WHERE claim_id = %s AND knower_entity_id = %s
        """,
        (claim_id, source_entity_id),
    )
    assert cur.fetchone()["acquired_at_world_time"] == birth_world_time
    return claim_id


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


def _chain(cur: Any, length: int) -> tuple[list[int], list[int]]:
    entities: list[int] = []
    characters: list[int] = []
    for index in range(length):
        entity, character = _insert_character(cur, f"chain-{index}")
        entities.append(entity)
        characters.append(character)
    for source, target in zip(characters, characters[1:]):
        _insert_relationship(cur, source, target)
    return entities, characters


def test_single_hop_ledgers_scheduled_time_provenance_and_policy(
    live_conn: Any,
) -> None:
    """One mature edge mints matching projection and payload-only event."""

    settings = _settings()
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        source, source_character = _insert_character(cur, "single-source")
        listener, listener_character = _insert_character(cur, "single-listener")
        _insert_relationship(cur, source_character, listener_character)
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
        "knower_entity_id": listener,
        "immediate_source_entity_id": source,
        "root_source_entity_id": source,
        "channel": "dyad:associate",
        "latency_seconds": 3600.0,
        "depth": 1,
        "policy_digest": contagion_policy_digest(settings),
    }
    assert participants == set()


def test_propagation_event_does_not_change_salience_or_hydration_feed() -> None:
    """Payload-only acquisitions stay out of actor and recent-event readers."""

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
                           SELECT 1 FROM information_schema.columns
                           WHERE table_schema = ANY(current_schemas(false))
                             AND table_name = 'world_events'
                             AND column_name = 'world_time'
                       ) AS shaped
                """
            )
            migration_state = cur.fetchone()
            if not migration_state["registered"] or not migration_state["shaped"]:
                pytest.skip(
                    "slot 5 has not applied migration 083: salience isolation "
                    "requires the real propagation ledger"
                )
            entities, _ = _chain(cur, 2)
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


def test_large_skip_drains_chained_hops_at_staggered_times(live_conn: Any) -> None:
    """A single fixpoint drain releases every mature hop, never at W."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 4)
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


def test_not_yet_mature_edge_waits(live_conn: Any) -> None:
    """An edge whose scheduled acquisition is later than W stays pending."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 2)
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


def test_fan_out_cap_uses_latency_then_listener_id(live_conn: Any) -> None:
    """Only the sorted first cap edges ever transmit for a knower/claim."""

    settings = _settings(neutral="2h", fan_out_cap=2)
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        source, source_character = _insert_character(cur, "fanout-source")
        low, low_character = _insert_character(cur, "fanout-low")
        high, high_character = _insert_character(cur, "fanout-high")
        slow, slow_character = _insert_character(cur, "fanout-slow")
        _insert_relationship(cur, source_character, high_character)
        _insert_relationship(cur, source_character, low_character)
        _insert_relationship(cur, source_character, slow_character, valence="0|neutral")
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


def test_depth_cap_is_recovered_across_separate_drains(live_conn: Any) -> None:
    """Persisted event depth releases hop two later and blocks hop three."""

    settings = _settings(depth_cap=2)
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 4)
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
    live_conn: Any,
) -> None:
    """Old bounded, private, and common claims retain only seeded awareness."""

    settings = _settings(trusting="3h", age_horizon="2h")
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        source, source_character = _insert_character(cur, "gating-source")
        _, listener_character = _insert_character(cur, "gating-listener")
        _insert_relationship(cur, source_character, listener_character)
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


def test_late_drain_lands_hop_scheduled_inside_age_horizon(live_conn: Any) -> None:
    """Hop eligibility uses its scheduled time, never narration cadence W."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 3)
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


def test_null_awareness_is_possession_terminal(live_conn: Any) -> None:
    """A clockless knower blocks re-minting but schedules no outbound hop."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        source, _ = _insert_character(cur, "terminal-source")
        terminal, terminal_character = _insert_character(cur, "terminal-knower")
        downstream, downstream_character = _insert_character(cur, "terminal-downstream")
        _insert_relationship(cur, terminal_character, downstream_character)
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
    live_conn: Any,
) -> None:
    """A genuinely clockless claim is legal history outside the frontier."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        source, source_character = _insert_character(cur, "clockless-source")
        listener, listener_character = _insert_character(cur, "clockless-listener")
        _insert_relationship(cur, source_character, listener_character)
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


def test_non_primary_commit_skips_propagation_drain(live_conn: Any) -> None:
    """Dream/flashback/atemporal-equivalent chunks never move knowledge."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 2)
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
    live_conn: Any,
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
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        faction = _insert_faction(cur, "cellular")
        listener, _ = _insert_character(cur, "cellular-listener")
        _insert_pair_tag(cur, faction, listener, "authority_over")
        _insert_culture_tag(cur, faction, "cellular_clandestine")
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


def test_idempotent_redrain_and_disabled_config_are_noops(live_conn: Any) -> None:
    """The awareness uniqueness key closes a drain; disabled reads nothing."""

    settings = _settings()
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 2)
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


def test_resolution_free_commit_still_drains(live_conn: Any) -> None:
    """An accepted tick with no proposal/resolutions still advances knowledge."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 2)
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


def test_replay_readmits_beneficiary_participant_awareness(
    live_conn: Any,
) -> None:
    """PR #520 review: beneficiary-role mints must survive reconstruction.

    PARTICIPANT_ROLES includes beneficiary; the readmission query must accept
    every role minting accepts, or valid rows reconstruct as drift.
    """

    beneficiary_settings = {**EPISTEMICS, "aware_roles": ["actor", "beneficiary"]}
    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 2)
        actor_id, beneficiary_id = entities[0], entities[1]
        base_chunk, _ = _insert_chunk(cur)
        with live_conn.cursor() as checkpoint_cur:
            checkpoint_id = capture_state_checkpoint_sync(
                checkpoint_cur, chunk_id=base_chunk, label="manual"
            )
        assert checkpoint_id is not None
        mint_chunk, birth_world_time = _insert_chunk(cur, time_delta=timedelta(hours=2))
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, actor_entity_id, world_layer,
                source, changed_fields, payload
            ) VALUES (
                'threat_issued', %s, %s, 'primary', 'resolver', '{}', '{}'::jsonb
            )
            RETURNING id
            """,
            (mint_chunk, actor_id),
        )
        event_id = int(cur.fetchone()["id"])
        cur.execute(
            """
            INSERT INTO world_event_entities (event_id, role, entity_id)
            VALUES (%s, 'actor', %s), (%s, 'beneficiary', %s)
            """,
            (event_id, actor_id, event_id, beneficiary_id),
        )
        minted = mint_claim_for_event(
            cur,
            world_event_id=event_id,
            event_type="threat_issued",
            summary="Rollback-only beneficiary claim.",
            participants=(
                ClaimParticipant(actor_id, "actor", "Actor", "character"),
                ClaimParticipant(
                    beneficiary_id, "beneficiary", "Beneficiary", "character"
                ),
            ),
            source_chunk_id=mint_chunk,
            source_resolution_id=None,
            settings=beneficiary_settings,
        )
        assert minted is not None
        live_rows = _awareness(cur, minted.claim_id)
        assert {int(r["knower_entity_id"]) for r in live_rows} == {
            actor_id,
            beneficiary_id,
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
    assert _canonical_rows(replayed_rows) == _canonical_rows(live_rows)


def test_replay_reconstructs_propagated_awareness_from_event(
    live_conn: Any,
) -> None:
    """The event ledger reproduces the live awareness projection after a drain."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        entities, _ = _chain(cur, 3)
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
    live_conn: Any,
) -> None:
    """A projection-only awareness INSERT is visible to the replay oracle."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        source, _ = _insert_character(cur, "drift-source")
        rogue, _ = _insert_character(cur, "drift-rogue")
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
    live_conn: Any,
) -> None:
    """Pre-section checkpoints remain verifiable through explicit skipping."""

    with live_conn.cursor(cursor_factory=RealDictCursor) as cur:
        source, _ = _insert_character(cur, "old-checkpoint-source")
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
async def test_async_drain_matches_sync_single_hop() -> None:
    """The async accepted-chunk twin mints the same scheduled ledger pair."""

    conn = await asyncpg.connect(get_slot_db_url(slot=LIVE_SLOT))
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
        if not migration_state["registered"] or not migration_state["shaped"]:
            pytest.skip(
                "slot 5 has not applied migration 083: async propagation "
                "coverage requires the registered event and shaped ledger"
            )
        source = int(
            await conn.fetchval(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('character', true) RETURNING id"
            )
        )
        listener = int(
            await conn.fetchval(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('character', true) RETURNING id"
            )
        )
        source_character = int(
            await conn.fetchval(
                "INSERT INTO characters (name, entity_id) "
                "VALUES ($1, $2) RETURNING id",
                f"propagation-async-source-{uuid4().hex[:10]}",
                source,
            )
        )
        listener_character = int(
            await conn.fetchval(
                "INSERT INTO characters (name, entity_id) "
                "VALUES ($1, $2) RETURNING id",
                f"propagation-async-listener-{uuid4().hex[:10]}",
                listener,
            )
        )
        await conn.execute(
            """
            INSERT INTO character_relationships (
                character1_id, character2_id, relationship_type,
                emotional_valence, dynamic, recent_events, history
            ) VALUES (
                $1, $2, 'associate', '+3|trusting',
                'Rollback-only Stage 2c conduit.', 'None.', 'Fixture.'
            )
            """,
            source_character,
            listener_character,
        )
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
        chunk_id,
        world_layer,
        time_delta,
        token[:10],
    )
    stamped = await conn.fetchval(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = $1", chunk_id
    )
    assert stamped is not None
    return chunk_id, stamped


def _canonical_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: canonicalize(value) for key, value in sorted(row.items())}
        for row in sorted(rows, key=lambda item: int(item["id"]))
    ]
