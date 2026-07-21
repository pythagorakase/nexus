"""Rollback-only live PostgreSQL coverage for durable backstory reveals."""

from __future__ import annotations

from datetime import datetime, timedelta
from itertools import count
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

from nexus.agents.orrery.epistemics import (
    author_backstory_secret_sync,
    mint_account_variant_sync,
)
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.reveal import drain_backstory_reveals_sync
from nexus.agents.orrery.substrate import WorldState
from nexus.api.slot_utils import get_slot_db_url


pytestmark = pytest.mark.requires_postgres
MIGRATION_SQL = Path("migrations/091_backstory_secrets.sql").read_text()
_SCENES = count(400)


@pytest.fixture()
def live_conn() -> Iterator[Any]:
    """Install migration 091 in a throwaway schema and roll back all writes."""

    conn = psycopg2.connect(get_slot_db_url(slot=5), cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT to_regclass('claims') IS NOT NULL AS claims_ready,
                       EXISTS (
                           SELECT 1
                           FROM information_schema.columns
                           WHERE table_schema = ANY(current_schemas(false))
                             AND table_name = 'claims'
                             AND column_name = 'account_label'
                       ) AS accounts_ready,
                       EXISTS (
                           SELECT 1
                           FROM information_schema.columns
                           WHERE table_schema = ANY(current_schemas(false))
                             AND table_name = 'world_events'
                             AND column_name = 'world_time'
                       ) AS event_clock_ready
                """
            )
            readiness = cur.fetchone()
            if not all(readiness.values()):
                pytest.skip("slot 5 requires applied migrations 083 and 090")
            schema = f"reveal_live_{uuid4().hex[:12]}"
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET LOCAL search_path = "{schema}", public')
            cur.execute(MIGRATION_SQL)
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _insert_chunk(
    cur: Any,
    *,
    world_layer: str = "primary",
    time_delta: timedelta = timedelta(0),
) -> tuple[int, datetime]:
    token = uuid4().hex[:12]
    cur.execute(
        """
        INSERT INTO narrative_chunks (raw_text, storyteller_text)
        VALUES (%s, 'Rollback-only backstory reveal fixture.')
        RETURNING id
        """,
        (f"Backstory reveal fixture {token}.",),
    )
    chunk_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO chunk_metadata (
            chunk_id, season, episode, scene, world_layer, time_delta,
            generation_date, slug
        ) VALUES (
            %s, 97, 97, %s, %s::world_layer_type, %s, now(), %s
        )
        """,
        (chunk_id, next(_SCENES), world_layer, time_delta, token[:10]),
    )
    cur.execute(
        "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s", (chunk_id,)
    )
    world_time = cur.fetchone()["world_time"]
    assert world_time is not None
    return chunk_id, world_time


def _insert_character(cur: Any, label: str, place_id: int) -> int:
    cur.execute(
        "INSERT INTO entities (kind, is_active) "
        "VALUES ('character', true) RETURNING id"
    )
    entity_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO characters (name, entity_id, current_location)
        VALUES (%s, %s, %s)
        """,
        (f"reveal-{label}-{uuid4().hex[:10]}", entity_id, place_id),
    )
    return entity_id


def _insert_private_incident(
    cur: Any,
    *,
    source_chunk_id: int,
    scope: str = "private",
) -> tuple[int, int, tuple[int, int, int], int]:
    cur.execute("SELECT id FROM places ORDER BY id LIMIT 1")
    place_id = int(cur.fetchone()["id"])
    holder = _insert_character(cur, "holder", place_id)
    first = _insert_character(cur, "first", place_id)
    second = _insert_character(cur, "second", place_id)
    cur.execute(
        """
        INSERT INTO world_events (
            event_type, tick_chunk_id, actor_entity_id, target_entity_id,
            world_layer, source, changed_fields, payload
        ) VALUES (
            'threat_issued', %s, %s, %s, 'primary', 'authored', '{}', '{}'
        )
        RETURNING id
        """,
        (source_chunk_id, holder, first),
    )
    event_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO world_event_entities (event_id, role, entity_id)
        VALUES (%s, 'actor', %s),
               (%s, 'target', %s),
               (%s, 'beneficiary', %s)
        """,
        (event_id, holder, event_id, first, event_id, second),
    )
    cur.execute(
        """
        INSERT INTO claims (
            world_event_id, account_label, summary, scope, source_chunk_id
        ) VALUES (%s, %s, 'A rollback-only backstory secret.', %s, %s)
        RETURNING id
        """,
        (event_id, f"canonical-{uuid4().hex[:8]}", scope, source_chunk_id),
    )
    claim_id = int(cur.fetchone()["id"])
    cur.execute(
        """
        INSERT INTO claim_awareness (
            claim_id, knower_entity_id, source_tier, source_chunk_id
        ) VALUES (%s, %s, 'participant', %s)
        """,
        (claim_id, holder, source_chunk_id),
    )
    return event_id, claim_id, (holder, first, second), place_id


def test_authoring_rejects_non_private_and_unregistered_gate(
    live_conn: Any,
) -> None:
    with live_conn.cursor() as cur:
        source_chunk_id, _ = _insert_chunk(cur)
        _, bounded_claim, participants, _ = _insert_private_incident(
            cur, source_chunk_id=source_chunk_id, scope="bounded"
        )
        with pytest.raises(ValueError, match="must be private"):
            author_backstory_secret_sync(
                cur,
                claim_id=bounded_claim,
                gate_template_id="holder_death",
                holder_entity_id=participants[0],
                source_chunk_id=source_chunk_id,
            )

        _, private_claim, private_participants, _ = _insert_private_incident(
            cur, source_chunk_id=source_chunk_id
        )
        with pytest.raises(ValueError, match="Unregistered reveal gate"):
            author_backstory_secret_sync(
                cur,
                claim_id=private_claim,
                gate_template_id="plot_convenience",
                holder_entity_id=private_participants[0],
                source_chunk_id=source_chunk_id,
            )


def test_commit_reveals_promotes_grants_once_and_redrain_is_noop(
    live_conn: Any,
) -> None:
    with live_conn.cursor() as cur:
        source_chunk_id, source_world_time = _insert_chunk(cur)
        _, claim_id, participants, place_id = _insert_private_incident(
            cur, source_chunk_id=source_chunk_id
        )
        holder, first, second = participants
        sibling_id = mint_account_variant_sync(
            cur,
            source_claim_id=claim_id,
            account_label=f"alternate-{uuid4().hex[:8]}",
            summary="A sibling account promoted with the incident.",
            source_chunk_id=source_chunk_id,
        )
        secret_id = author_backstory_secret_sync(
            cur,
            claim_id=claim_id,
            gate_template_id="participants_reunited",
            holder_entity_id=holder,
            source_chunk_id=source_chunk_id,
        )
        tick_chunk_id, tick_world_time = _insert_chunk(
            cur, time_delta=timedelta(hours=2)
        )

    state = WorldState(
        is_active={holder: True, first: True, second: True},
        locations={holder: place_id, first: place_id, second: place_id},
        world_time=tick_world_time,
    )
    first_result = commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=tick_chunk_id,
        reveal_settings={"enabled": True},
        reveal_state=state,
    )
    second_result = commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=tick_chunk_id,
        reveal_settings={"enabled": True},
        reveal_state=state,
    )

    assert first_result.reveal_count == 1
    assert second_result.reveal_count == 0
    with live_conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, revealed_at_world_time, revealed_by_chunk_id
            FROM backstory_secrets WHERE id = %s
            """,
            (secret_id,),
        )
        assert cur.fetchone() == {
            "status": "revealed",
            "revealed_at_world_time": tick_world_time,
            "revealed_by_chunk_id": tick_chunk_id,
        }
        cur.execute(
            "SELECT id, scope FROM claims WHERE id IN (%s, %s) ORDER BY id",
            (claim_id, sibling_id),
        )
        assert [row["scope"] for row in cur.fetchall()] == ["bounded", "bounded"]
        cur.execute(
            """
            SELECT knower_entity_id, source_tier, immediate_source_entity_id,
                   acquired_at_world_time
            FROM claim_awareness
            WHERE claim_id = %s
            ORDER BY knower_entity_id
            """,
            (claim_id,),
        )
        awareness = cur.fetchall()
        assert [row["knower_entity_id"] for row in awareness] == sorted(participants)
        told = [row for row in awareness if row["knower_entity_id"] != holder]
        assert all(row["source_tier"] == "told" for row in told)
        assert all(row["immediate_source_entity_id"] == holder for row in told)
        assert all(row["acquired_at_world_time"] == tick_world_time for row in told)
        cur.execute(
            """
            SELECT actor_entity_id, payload, world_time
            FROM world_events
            WHERE event_type = 'backstory_revealed'
              AND (payload ->> 'secret_id')::bigint = %s
            """,
            (secret_id,),
        )
        events = cur.fetchall()
        assert len(events) == 1
        assert events[0]["actor_entity_id"] == holder
        assert events[0]["world_time"] == tick_world_time
        assert events[0]["payload"]["claim_id"] == claim_id
        assert events[0]["payload"]["gate_template_id"] == ("participants_reunited")
        assert events[0]["payload"]["revealed_participant_entity_ids"] == sorted(
            [first, second]
        )
        cur.execute(
            """
            SELECT world_time, payload
            FROM world_events
            WHERE event_type = 'backstory_secret_authored'
              AND (payload ->> 'secret_id')::bigint = %s
            """,
            (secret_id,),
        )
        authored = cur.fetchone()
        assert authored["world_time"] == source_world_time
        assert authored["payload"]["claim_id"] == claim_id


def test_unregistered_gate_in_latent_row_raises_loudly(live_conn: Any) -> None:
    with live_conn.cursor() as cur:
        source_chunk_id, _ = _insert_chunk(cur)
        _, claim_id, participants, _ = _insert_private_incident(
            cur, source_chunk_id=source_chunk_id
        )
        cur.execute(
            """
            INSERT INTO backstory_secrets (
                claim_id, gate_template_id, holder_entity_id, source_chunk_id
            ) VALUES (%s, 'missing_gate', %s, %s)
            """,
            (claim_id, participants[0], source_chunk_id),
        )
        tick_chunk_id, _ = _insert_chunk(cur, time_delta=timedelta(hours=1))
        with pytest.raises(RuntimeError, match="Unregistered reveal gate"):
            drain_backstory_reveals_sync(
                cur,
                tick_chunk_id=tick_chunk_id,
                settings={"enabled": True},
                state=WorldState(is_active={participants[0]: False}),
            )


@pytest.mark.parametrize(
    ("world_layer", "settings"),
    [("retrograde", {"enabled": True}), ("primary", {"enabled": False})],
)
def test_world_layer_and_disabled_config_leave_secret_latent(
    live_conn: Any,
    world_layer: str,
    settings: dict[str, bool],
) -> None:
    with live_conn.cursor() as cur:
        source_chunk_id, _ = _insert_chunk(cur)
        _, claim_id, participants, _ = _insert_private_incident(
            cur, source_chunk_id=source_chunk_id
        )
        secret_id = author_backstory_secret_sync(
            cur,
            claim_id=claim_id,
            gate_template_id="holder_death",
            holder_entity_id=participants[0],
            source_chunk_id=source_chunk_id,
        )
        tick_chunk_id, _ = _insert_chunk(
            cur,
            world_layer=world_layer,
            time_delta=timedelta(hours=1),
        )
        result = drain_backstory_reveals_sync(
            cur,
            tick_chunk_id=tick_chunk_id,
            settings=settings,
            state=WorldState(is_active={participants[0]: False}),
        )
        assert result.revealed_count == 0
        cur.execute("SELECT status FROM backstory_secrets WHERE id = %s", (secret_id,))
        assert cur.fetchone()["status"] == "latent"
