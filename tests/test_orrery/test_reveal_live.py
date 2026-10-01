"""Rollback-only live PostgreSQL coverage for durable backstory reveals.

The tests run on one module-scoped disposable template clone seeded with a
zoned place, a protagonist standing there, and a story clock, so no owner save
slot is opened. The synchronous fixture then commits each test's incident
cast (holder, first, second) at that place through ``seed_character``, plus
the next-tick recipient and its conduit from the same-tick holder through
``seed_relationship``. Each test's own writes (the incident's event, claim,
awareness, and secret) stay inside one transaction that always rolls back.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path
from typing import Any, Iterator, Mapping, NamedTuple
from uuid import uuid4

import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]

from nexus.agents.orrery.epistemics import (
    author_backstory_secret_async,
    author_backstory_secret_sync,
    mint_account_variant_sync,
)
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.reveal import drain_backstory_reveals_sync
from nexus.agents.orrery.reconstruction import capture_state_checkpoint_sync
from nexus.agents.orrery.replay import verify_checkpoints_sync
from nexus.agents.orrery.substrate import WorldState
from tests.pg_fixtures import (
    asyncpg_kwargs,
    connect,
    disposable_slot_database,
    seed_character,
    seed_place,
    seed_protagonist,
    seed_story_clock,
    seed_zone,
)
from tests.test_orrery.claim_accounts_test_support import (
    _install_valence_shadow,
    _settings,
    install_claim_accounts_shadow_async,
    seed_conduit,
)


pytestmark = pytest.mark.requires_postgres
MIGRATION_SQL = Path("migrations/091_backstory_secrets.sql").read_text()
ACCOUNT_MIGRATION_SQL = Path("migrations/090_claim_accounts.sql").read_text()
DISTORTION_MIGRATION_SQL = Path("migrations/092_claim_distortion_depth.sql").read_text()
_SCENES = count(400)
# The first story-clock instant: base_timestamp and the bootstrap chunk's clock.
STORY_CLOCK = datetime(2100, 1, 1, 6, tzinfo=timezone.utc)
REVEAL_PLACE_NAME = "Reveal Square"
# One committed incident cast per incident a test builds; the parametrized
# world-layer test reuses its cast, since each case rolls back.
CAST_KEYS = (
    "bounded",
    "private",
    "grant_completes",
    "commit_reveals",
    "same_tick",
    "unregistered_gate",
    "world_layer",
    "replay",
)


class RevealClone(NamedTuple):
    """The module's seeded clone and the rows each reveal test names."""

    dbname: str
    place_id: int
    protagonist_entity_id: int
    clock_chunk_id: int
    casts: Mapping[str, tuple[int, int, int]]
    outsider_entity_id: int


def _install_claim_schema(cur: Any) -> None:
    """Install migrations 090 and 092 in the rollback-only reveal schema."""

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
    cur.execute(ACCOUNT_MIGRATION_SQL)
    cur.execute(DISTORTION_MIGRATION_SQL)


@pytest.fixture(scope="module")
def reveal_clone() -> Iterator[RevealClone]:
    """Seed a zoned place, a protagonist there, the story clock, then the casts.

    Each incident cast (holder, first, second entity IDs) stands at the place
    and is committed through ``seed_character``; the same-tick test's
    next-tick recipient stands there too, reached from that cast's holder by a
    trusting conduit committed through ``seed_relationship``.
    """

    with disposable_slot_database("qa885_reveal") as dbname:
        seed_zone(
            dbname,
            name="Reveal Zone",
            min_longitude=-74.1,
            min_latitude=40.6,
            max_longitude=-73.8,
            max_latitude=40.9,
        )
        place_id, _ = seed_place(dbname, name=REVEAL_PLACE_NAME)
        _, protagonist_entity_id = seed_protagonist(
            dbname,
            base_timestamp=STORY_CLOCK.isoformat(),
            current_location=place_id,
        )
        clock_chunk_id = seed_story_clock(dbname, world_time=STORY_CLOCK)
        casts: dict[str, tuple[int, int, int]] = {}
        holder_characters: dict[str, int] = {}
        for key in CAST_KEYS:
            seeded = [
                seed_character(
                    dbname, name=f"reveal-{key}-{role}", current_location=place_id
                )
                for role in ("holder", "first", "second")
            ]
            holder_characters[key] = seeded[0][0]
            casts[key] = (seeded[0][1], seeded[1][1], seeded[2][1])
        outsider_character, outsider_entity_id = seed_character(
            dbname,
            name="reveal-same_tick-next-tick-recipient",
            current_location=place_id,
        )
        seed_conduit(dbname, holder_characters["same_tick"], outsider_character)
        yield RevealClone(
            dbname=dbname,
            place_id=place_id,
            protagonist_entity_id=protagonist_entity_id,
            clock_chunk_id=clock_chunk_id,
            casts=casts,
            outsider_entity_id=outsider_entity_id,
        )


@pytest.fixture()
def live_conn(reveal_clone: RevealClone) -> Iterator[Any]:
    """Install migration 091 in a throwaway schema and roll back all writes."""

    with closing(connect(reveal_clone.dbname, cursor_factory=RealDictCursor)) as conn:
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
                assert readiness == {
                    "claims_ready": True,
                    "accounts_ready": True,
                    "event_clock_ready": True,
                }, f"the head-migrated clone lacks migrations 083/090: {readiness}"
                schema = f"reveal_live_{uuid4().hex[:12]}"
                cur.execute(f'CREATE SCHEMA "{schema}"')
                cur.execute(f'SET LOCAL search_path = "{schema}", public')
                _install_claim_schema(cur)
                cur.execute(MIGRATION_SQL)
                _install_valence_shadow(cur)
            yield conn
        finally:
            conn.rollback()


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


def _insert_private_incident(
    cur: Any,
    *,
    cast: tuple[int, int, int],
    place_id: int,
    source_chunk_id: int,
    scope: str = "private",
    holder_aware: bool = True,
) -> tuple[int, int, tuple[int, int, int], int]:
    """Stage one private incident among a committed cast, in-transaction."""

    cur.execute("SELECT name FROM places WHERE id = %s", (place_id,))
    place = cur.fetchone()
    assert place is not None and place["name"] == REVEAL_PLACE_NAME, place
    holder, first, second = cast
    cur.execute(
        """
        SELECT count(*) AS located
        FROM characters
        WHERE entity_id = ANY(%s) AND current_location = %s
        """,
        (list(cast), place_id),
    )
    assert cur.fetchone()["located"] == 3, "the seeded cast stands at the place"
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
    if holder_aware:
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
    reveal_clone: RevealClone,
) -> None:
    with live_conn.cursor() as cur:
        source_chunk_id, source_world_time = _insert_chunk(cur)
        _, bounded_claim, participants, _ = _insert_private_incident(
            cur,
            cast=reveal_clone.casts["bounded"],
            place_id=reveal_clone.place_id,
            source_chunk_id=source_chunk_id,
            scope="bounded",
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
            cur,
            cast=reveal_clone.casts["private"],
            place_id=reveal_clone.place_id,
            source_chunk_id=source_chunk_id,
        )
        with pytest.raises(ValueError, match="Unregistered reveal gate"):
            author_backstory_secret_sync(
                cur,
                claim_id=private_claim,
                gate_template_id="plot_convenience",
                holder_entity_id=private_participants[0],
                source_chunk_id=source_chunk_id,
            )


def test_authoring_grants_unpossessed_holder_and_reveal_completes(
    live_conn: Any,
    reveal_clone: RevealClone,
) -> None:
    with live_conn.cursor() as cur:
        source_chunk_id, source_world_time = _insert_chunk(cur)
        _, claim_id, participants, place_id = _insert_private_incident(
            cur,
            cast=reveal_clone.casts["grant_completes"],
            place_id=reveal_clone.place_id,
            source_chunk_id=source_chunk_id,
            holder_aware=False,
        )
        holder, first, second = participants
        secret_id = author_backstory_secret_sync(
            cur,
            claim_id=claim_id,
            gate_template_id="holder_death",
            holder_entity_id=holder,
            source_chunk_id=source_chunk_id,
        )
        cur.execute(
            """
            SELECT source_tier, immediate_source_entity_id,
                   acquired_at_world_time, source_chunk_id
            FROM claim_awareness
            WHERE claim_id = %s AND knower_entity_id = %s
            """,
            (claim_id, holder),
        )
        assert cur.fetchone() == {
            "source_tier": "granted",
            "immediate_source_entity_id": None,
            "acquired_at_world_time": source_world_time,
            "source_chunk_id": source_chunk_id,
        }
        tick_chunk_id, tick_world_time = _insert_chunk(
            cur,
            time_delta=timedelta(hours=1),
        )
        result = drain_backstory_reveals_sync(
            cur,
            tick_chunk_id=tick_chunk_id,
            settings={"enabled": True},
            state=WorldState(
                is_active={holder: False, first: True, second: True},
                locations={holder: place_id, first: place_id, second: place_id},
                world_time=tick_world_time,
            ),
        )
        assert result.secret_ids == (secret_id,)
        cur.execute(
            "SELECT status FROM backstory_secrets WHERE id = %s",
            (secret_id,),
        )
        assert cur.fetchone()["status"] == "revealed"
        cur.execute(
            """
            SELECT knower_entity_id
            FROM claim_awareness
            WHERE claim_id = %s
            ORDER BY knower_entity_id
            """,
            (claim_id,),
        )
        assert [row["knower_entity_id"] for row in cur.fetchall()] == sorted(
            participants
        )


def test_async_authoring_grants_unpossessed_holder(
    reveal_clone: RevealClone,
) -> None:
    import asyncio

    import asyncpg  # type: ignore[import-untyped]

    async def run() -> None:
        conn = await asyncpg.connect(**asyncpg_kwargs(reveal_clone.dbname))
        transaction = conn.transaction()
        await transaction.start()
        try:
            schema = f"reveal_async_{uuid4().hex[:12]}"
            await conn.execute(f'CREATE SCHEMA "{schema}"')
            await conn.execute(f'SET LOCAL search_path = "{schema}", public')
            await install_claim_accounts_shadow_async(conn)
            await conn.execute(
                """
                DROP TABLE backstory_secrets;
                CREATE TEMP TABLE backstory_secrets (
                    id bigserial PRIMARY KEY,
                    claim_id bigint NOT NULL UNIQUE,
                    gate_template_id text NOT NULL,
                    status text NOT NULL DEFAULT 'latent'
                        CHECK (status IN ('latent', 'revealed', 'retired')),
                    holder_entity_id bigint NOT NULL,
                    source_chunk_id bigint,
                    revealed_at_world_time timestamptz,
                    revealed_by_chunk_id bigint,
                    created_at timestamptz NOT NULL DEFAULT now()
                ) ON COMMIT DROP;
                INSERT INTO event_types (
                    type, category, severity, description
                ) VALUES (
                    'backstory_secret_authored', 'revelation', 'minor',
                    'Async rollback-only authoring fixture.'
                ) ON CONFLICT (type) DO NOTHING;
                """
            )
            clock = await conn.fetchrow(
                """
                SELECT metadata.chunk_id, metadata.world_time,
                       entity.id AS holder_entity_id
                FROM chunk_metadata metadata
                CROSS JOIN LATERAL (
                    SELECT id FROM entities WHERE kind = 'character'
                    ORDER BY id LIMIT 1
                ) entity
                WHERE metadata.world_time IS NOT NULL
                ORDER BY metadata.chunk_id DESC
                LIMIT 1
                """
            )
            assert clock is not None
            # The seeded story clock is the head chunk and the seeded
            # protagonist is the lowest character entity.
            assert clock["chunk_id"] == reveal_clone.clock_chunk_id
            assert clock["world_time"] == STORY_CLOCK
            assert clock["holder_entity_id"] == reveal_clone.protagonist_entity_id
            holder_place = await conn.fetchrow(
                """
                SELECT pl.id, pl.name
                FROM characters ch
                JOIN places pl ON pl.id = ch.current_location
                WHERE ch.entity_id = $1
                """,
                clock["holder_entity_id"],
            )
            assert holder_place is not None
            assert dict(holder_place) == {
                "id": reveal_clone.place_id,
                "name": REVEAL_PLACE_NAME,
            }
            event_id = await conn.fetchval(
                """
                INSERT INTO world_events (
                    event_type, tick_chunk_id, actor_entity_id, world_layer,
                    source, changed_fields, payload
                ) VALUES (
                    'threat_issued', $1, $2, 'primary',
                    'authored', '{}', '{}'::jsonb
                )
                RETURNING id
                """,
                clock["chunk_id"],
                clock["holder_entity_id"],
            )
            claim_id = await conn.fetchval(
                """
                INSERT INTO claims (
                    world_event_id, account_label, summary, scope,
                    source_chunk_id
                ) VALUES ($1, $2, 'Async holder grant fixture.', 'private', $3)
                RETURNING id
                """,
                event_id,
                f"async-secret-{uuid4().hex[:8]}",
                clock["chunk_id"],
            )
            await author_backstory_secret_async(
                conn,
                claim_id=int(claim_id),
                gate_template_id="holder_death",
                holder_entity_id=int(clock["holder_entity_id"]),
                source_chunk_id=int(clock["chunk_id"]),
            )
            awareness = await conn.fetchrow(
                """
                SELECT source_tier, immediate_source_entity_id,
                       acquired_at_world_time, source_chunk_id
                FROM claim_awareness
                WHERE claim_id = $1 AND knower_entity_id = $2
                """,
                claim_id,
                clock["holder_entity_id"],
            )
            assert awareness is not None
            assert dict(awareness) == {
                "source_tier": "granted",
                "immediate_source_entity_id": None,
                "acquired_at_world_time": clock["world_time"],
                "source_chunk_id": clock["chunk_id"],
            }
        finally:
            await transaction.rollback()
            await conn.close()

    asyncio.run(run())


def test_commit_reveals_promotes_grants_once_and_redrain_is_noop(
    live_conn: Any,
    reveal_clone: RevealClone,
) -> None:
    with live_conn.cursor() as cur:
        source_chunk_id, source_world_time = _insert_chunk(cur)
        _, claim_id, participants, place_id = _insert_private_incident(
            cur,
            cast=reveal_clone.casts["commit_reveals"],
            place_id=reveal_clone.place_id,
            source_chunk_id=source_chunk_id,
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


def test_same_tick_reveal_waits_until_next_tick_to_propagate(
    live_conn: Any,
    reveal_clone: RevealClone,
) -> None:
    """Reveal promotion misses this tick's snapshot and enters the next."""

    with live_conn.cursor() as cur:
        source_chunk_id, source_world_time = _insert_chunk(cur)
        incident_id, claim_id, participants, place_id = _insert_private_incident(
            cur,
            cast=reveal_clone.casts["same_tick"],
            place_id=reveal_clone.place_id,
            source_chunk_id=source_chunk_id,
        )
        holder, same_tick_recipient, _ = participants
        cur.execute(
            """
            UPDATE claim_awareness
            SET acquired_at_world_time = %s
            WHERE claim_id = %s AND knower_entity_id = %s
            """,
            (source_world_time, claim_id, holder),
        )
        variant_id = mint_account_variant_sync(
            cur,
            source_claim_id=claim_id,
            account_label=f"next-scene-gossip-{uuid4().hex[:8]}",
            summary="The next-scene distorted account.",
            source_chunk_id=source_chunk_id,
            distortion_min_depth=1,
        )
        author_backstory_secret_sync(
            cur,
            claim_id=claim_id,
            gate_template_id="participants_reunited",
            holder_entity_id=holder,
            source_chunk_id=source_chunk_id,
        )
        outsider = reveal_clone.outsider_entity_id
        cur.execute(
            """
            SELECT relationship_type, emotional_valence
            FROM character_relationships cr
            JOIN characters teller ON teller.id = cr.character1_id
            JOIN characters listener ON listener.id = cr.character2_id
            WHERE teller.entity_id = %s AND listener.entity_id = %s
            """,
            (holder, outsider),
        )
        assert cur.fetchone() == {
            "relationship_type": "associate",
            "emotional_valence": "+3|trusting",
        }, "the seeded holder-to-recipient conduit reaches the valence shadow"
        reveal_chunk_id, reveal_world_time = _insert_chunk(
            cur, time_delta=timedelta(hours=2)
        )

    reveal_state = WorldState(
        is_active={entity_id: True for entity_id in (*participants, outsider)},
        locations={entity_id: place_id for entity_id in (*participants, outsider)},
        world_time=reveal_world_time,
    )
    same_tick = commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=reveal_chunk_id,
        contagion_settings=_settings(),
        distortion_settings={"enabled": True},
        reveal_settings={"enabled": True},
        reveal_state=reveal_state,
    )

    with live_conn.cursor() as cur:
        cur.execute(
            """
            SELECT claim_id, knower_entity_id
            FROM claim_awareness
            WHERE claim_id IN (%s, %s)
            ORDER BY claim_id, knower_entity_id
            """,
            (claim_id, variant_id),
        )
        same_tick_awareness = {
            (int(row["claim_id"]), int(row["knower_entity_id"]))
            for row in cur.fetchall()
        }
        cur.execute(
            """
            SELECT count(*) AS count
            FROM world_events
            WHERE event_type = 'claim_propagated'
              AND tick_chunk_id = %s
              AND (payload ->> 'incident_world_event_id')::bigint = %s
            """,
            (reveal_chunk_id, incident_id),
        )
        same_tick_event_count = int(cur.fetchone()["count"])
        next_chunk_id, _ = _insert_chunk(cur, time_delta=timedelta(hours=1))

    assert same_tick.reveal_count == 1
    assert same_tick.propagation_count == 0
    assert same_tick_event_count == 0
    assert (claim_id, same_tick_recipient) in same_tick_awareness
    assert (claim_id, outsider) not in same_tick_awareness
    assert (variant_id, outsider) not in same_tick_awareness

    next_tick = commit_orrery_tick_sync(
        live_conn,
        None,
        tick_chunk_id=next_chunk_id,
        contagion_settings=_settings(),
        distortion_settings={"enabled": True},
    )
    with live_conn.cursor() as cur:
        cur.execute(
            """
            SELECT claim_id, knower_entity_id
            FROM claim_awareness
            WHERE claim_id IN (%s, %s)
            ORDER BY claim_id, knower_entity_id
            """,
            (claim_id, variant_id),
        )
        next_tick_awareness = {
            (int(row["claim_id"]), int(row["knower_entity_id"]))
            for row in cur.fetchall()
        }

    assert next_tick.propagation_count == 1
    assert (variant_id, outsider) in next_tick_awareness
    # Suppression contract: hearing any incident sibling blocks every later
    # account, so this same-tick canonical recipient never receives the variant.
    assert (variant_id, same_tick_recipient) not in next_tick_awareness


def test_unregistered_gate_in_latent_row_raises_loudly(
    live_conn: Any,
    reveal_clone: RevealClone,
) -> None:
    with live_conn.cursor() as cur:
        source_chunk_id, _ = _insert_chunk(cur)
        _, claim_id, participants, _ = _insert_private_incident(
            cur,
            cast=reveal_clone.casts["unregistered_gate"],
            place_id=reveal_clone.place_id,
            source_chunk_id=source_chunk_id,
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
    reveal_clone: RevealClone,
    world_layer: str,
    settings: dict[str, bool],
) -> None:
    with live_conn.cursor() as cur:
        source_chunk_id, _ = _insert_chunk(cur)
        _, claim_id, participants, _ = _insert_private_incident(
            cur,
            cast=reveal_clone.casts["world_layer"],
            place_id=reveal_clone.place_id,
            source_chunk_id=source_chunk_id,
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


def test_authored_and_revealed_secrets_replay_between_checkpoints(
    live_conn: Any,
    reveal_clone: RevealClone,
) -> None:
    with live_conn.cursor() as cur:
        base_chunk, _ = _insert_chunk(cur)
        _, claim_id, participants, _ = _insert_private_incident(
            cur,
            cast=reveal_clone.casts["replay"],
            place_id=reveal_clone.place_id,
            source_chunk_id=base_chunk,
        )
        holder = participants[0]
        base_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=base_chunk,
            label="manual",
        )
        assert base_id is not None

        authored_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=1))
        secret_id = author_backstory_secret_sync(
            cur,
            claim_id=claim_id,
            gate_template_id="holder_death",
            holder_entity_id=holder,
            source_chunk_id=authored_chunk,
        )
        authored_checkpoint_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=authored_chunk,
            label="manual",
        )
        assert authored_checkpoint_id is not None

        reveal_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=1))
        result = drain_backstory_reveals_sync(
            cur,
            tick_chunk_id=reveal_chunk,
            settings={"enabled": True},
            state=WorldState(is_active={holder: False}),
        )
        assert result.secret_ids == (secret_id,)
        revealed_checkpoint_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=reveal_chunk,
            label="manual",
        )
        assert revealed_checkpoint_id is not None

    with live_conn.cursor(cursor_factory=psycopg2.extensions.cursor) as cur:
        verdicts = verify_checkpoints_sync(cur)

    authored_verdict = next(
        verdict
        for verdict in verdicts
        if verdict.base_checkpoint_id == base_id
        and verdict.target_checkpoint_id == authored_checkpoint_id
    )
    revealed_verdict = next(
        verdict
        for verdict in verdicts
        if verdict.base_checkpoint_id == authored_checkpoint_id
        and verdict.target_checkpoint_id == revealed_checkpoint_id
    )
    assert not [
        drift
        for verdict in (authored_verdict, revealed_verdict)
        for drift in verdict.drifts
        if drift.section == "backstory_secrets"
    ]


def test_verify_skips_checkpoint_that_predates_backstory_section(
    live_conn: Any,
) -> None:
    with live_conn.cursor() as cur:
        base_chunk, _ = _insert_chunk(cur)
        base_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=base_chunk,
            label="manual",
        )
        assert base_id is not None
        cur.execute(
            "UPDATE state_checkpoints SET state = state - 'backstory_secrets' "
            "WHERE id = %s",
            (base_id,),
        )
        target_chunk, _ = _insert_chunk(cur, time_delta=timedelta(hours=1))
        target_id = capture_state_checkpoint_sync(
            cur,
            chunk_id=target_chunk,
            label="manual",
        )
        assert target_id is not None

    with live_conn.cursor(cursor_factory=psycopg2.extensions.cursor) as cur:
        verdicts = verify_checkpoints_sync(cur)

    verdict = next(
        item
        for item in verdicts
        if item.base_checkpoint_id == base_id and item.target_checkpoint_id == target_id
    )
    assert not [
        drift for drift in verdict.drifts if drift.section == "backstory_secrets"
    ]
    assert verdict.skipped_unreproducible >= 1
    assert any(
        "comparison skipped" in note
        for note in verdict.notes.get("backstory_secrets", [])
    )
