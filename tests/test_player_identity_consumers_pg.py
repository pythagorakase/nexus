"""PostgreSQL coverage for canonical player-identity consumers.

The module clones ``NEXUS_template`` with the dump-based new-story helper,
then rolls each consumer fixture back inside that disposable database. No
save-slot or template database is mutated.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator

import asyncpg  # type: ignore[import-untyped]
import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2 import sql  # type: ignore[import-untyped]
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from nexus.agents.lore.utils.entity_queries import (
    fetch_all_characters_with_references,
)
from nexus.agents.orrery.geo import story_active_zone_async
from nexus.agents.orrery.player_identity import (
    PlayerIdentityNotEstablishedError,
    canonical_player_character_id,
)
from nexus.agents.orrery.resolver import resolve_dry_run
from nexus.api import db_pool
from scripts import new_story_setup


pytestmark = pytest.mark.requires_postgres

_WORLD_TIME = datetime(2198, 4, 7, 16, 30, tzinfo=timezone.utc)
_AMBIENT_SETTINGS = {
    "max_seeds": 2,
    "per_dyad_cooldown_turns": 3,
    "expiry_turns": 2,
    "line_budget": 4,
    "turn_budget": 2,
}


def _connect(dbname: str) -> Any:
    """Open a direct psycopg connection to the disposable database."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


def _database_url(dbname: str) -> URL:
    """Build the SQLAlchemy URL for a disposable local database."""

    return URL.create(
        "postgresql+psycopg2",
        username=os.environ.get("PGUSER", "pythagor"),
        password=os.environ.get("PGPASSWORD"),
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5432")),
        database=dbname,
    )


@pytest.fixture(scope="module")
def disposable_player_db() -> Iterator[tuple[str, Engine]]:
    """Yield one dump-cloned scratch database and always drop it afterward."""

    dbname = f"qa_player_identity_{uuid.uuid4().hex[:10]}"
    admin: Any = None
    engine: Engine | None = None
    original_use_pool = new_story_setup.USE_POOL
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        new_story_setup.USE_POOL = False
        new_story_setup.initialize_slot_database(
            dbname,
            source_db="NEXUS_template",
        )
        engine = create_engine(_database_url(dbname), future=True)
        yield dbname, engine
    finally:
        new_story_setup.USE_POOL = original_use_pool
        if engine is not None:
            engine.dispose()
        pool = db_pool._pools.pop(dbname, None)
        if pool is not None:
            pool.closeall()
        if admin is not None:
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


@pytest.fixture()
def player_session(
    disposable_player_db: tuple[str, Engine],
) -> Iterator[Session]:
    """Yield a rollback-only SQLAlchemy session in the disposable save."""

    _dbname, engine = disposable_player_db
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _insert_character(
    session: Session,
    *,
    label: str,
    place_id: int,
) -> tuple[int, int]:
    """Insert one active character entity at the shared fixture place."""

    entity_id = int(
        session.execute(
            text(
                """
                INSERT INTO entities (kind, is_active)
                VALUES ('character', true)
                RETURNING id
                """
            )
        ).scalar_one()
    )
    character_id = int(
        session.execute(
            text(
                """
                INSERT INTO characters (
                    name, summary, current_activity, current_location, entity_id
                ) VALUES (
                    :name, :summary, 'waiting', :place_id, :entity_id
                )
                RETURNING id
                """
            ),
            {
                "name": f"identity-{label}-{uuid.uuid4().hex[:8]}",
                "summary": f"Canonical identity consumer fixture {label}.",
                "place_id": place_id,
                "entity_id": entity_id,
            },
        ).scalar_one()
    )
    return character_id, entity_id


def _seed_consumer_save(
    session: Session,
    *,
    establish_protagonist: bool,
) -> dict[str, Any]:
    """Seed actual resolver/context tables with an optional player identity."""

    session.execute(
        text(
            """
            UPDATE global_variables
            SET user_character = NULL,
                base_timestamp = :world_time,
                setting = '{"story_seed":{"weather":"clear"}}'::jsonb
            WHERE id = true
            """
        ),
        {"world_time": _WORLD_TIME},
    )
    place_entity_id = int(
        session.execute(
            text(
                """
                INSERT INTO entities (kind, is_active)
                VALUES ('place', true)
                RETURNING id
                """
            )
        ).scalar_one()
    )
    place_id = int(
        session.execute(
            text(
                """
                INSERT INTO places (name, type, summary, entity_id)
                VALUES (:name, 'fixed_location', :summary, :entity_id)
                RETURNING id
                """
            ),
            {
                "name": f"identity-place-{uuid.uuid4().hex[:8]}",
                "summary": "Rollback-only canonical identity fixture.",
                "entity_id": place_entity_id,
            },
        ).scalar_one()
    )
    characters = {
        label: _insert_character(session, label=label, place_id=place_id)
        for label in ("player", "mara", "vale")
    }
    chunk_id = int(
        session.execute(
            text(
                """
                INSERT INTO narrative_chunks (raw_text, storyteller_text)
                VALUES (
                    'Canonical identity consumer input.',
                    'Mara and Vale wait with the player.'
                )
                RETURNING id
                """
            )
        ).scalar_one()
    )
    session.execute(
        text(
            """
            INSERT INTO chunk_metadata (chunk_id, world_time)
            VALUES (:chunk_id, :world_time)
            """
        ),
        {"chunk_id": chunk_id, "world_time": _WORLD_TIME},
    )
    session.execute(
        text(
            """
            UPDATE chunk_metadata
            SET world_time = :world_time
            WHERE chunk_id = :chunk_id
            """
        ),
        {"chunk_id": chunk_id, "world_time": _WORLD_TIME},
    )
    for character_id, _entity_id in characters.values():
        session.execute(
            text(
                """
                INSERT INTO chunk_character_references (
                    chunk_id, character_id, reference
                ) VALUES (:chunk_id, :character_id, 'present')
                """
            ),
            {"chunk_id": chunk_id, "character_id": character_id},
        )
    for source_label, target_label in (("player", "mara"), ("mara", "vale")):
        session.execute(
            text(
                """
                INSERT INTO character_relationships (
                    character1_id, character2_id, relationship_type,
                    emotional_valence, dynamic, recent_events, history
                ) VALUES (
                    :source_id, :target_id, 'associate', '+1|favorable',
                    'Rollback-only identity fixture.', 'No persistent events.',
                    'Created for canonical player identity coverage.'
                )
                """
            ),
            {
                "source_id": characters[source_label][0],
                "target_id": characters[target_label][0],
            },
        )
    if establish_protagonist:
        session.execute(
            text(
                """
                UPDATE global_variables
                SET user_character = :character_id
                WHERE id = true
                """
            ),
            {"character_id": characters["player"][0]},
        )
    return {
        "chunk_id": chunk_id,
        "characters": characters,
    }


def test_ambient_resolver_excludes_established_protagonist(
    player_session: Session,
) -> None:
    """The real resolver produces only NPC ambient dyads for a valid save."""

    fixture = _seed_consumer_save(player_session, establish_protagonist=True)
    proposal = resolve_dry_run(
        player_session,
        (),
        anchor_chunk_id=fixture["chunk_id"],
        window_chunks=30,
        epistemics_settings={},
        ambient_settings=_AMBIENT_SETTINGS,
        ambient_pacing_allowed=True,
    )

    player_entity_id = fixture["characters"]["player"][1]
    npc_entity_ids = {
        fixture["characters"]["mara"][1],
        fixture["characters"]["vale"][1],
    }
    assert proposal.ambient_scene_seeds
    assert any(
        {participant.entity_id for participant in seed.participants} == npc_entity_ids
        for seed in proposal.ambient_scene_seeds
    )
    assert all(
        player_entity_id
        not in {participant.entity_id for participant in seed.participants}
        for seed in proposal.ambient_scene_seeds
    )


def test_ambient_resolver_rejects_save_without_protagonist(
    player_session: Session,
) -> None:
    """The real resolver no longer interprets a missing player as includable."""

    fixture = _seed_consumer_save(player_session, establish_protagonist=False)

    with pytest.raises(
        PlayerIdentityNotEstablishedError,
        match="user_character is NULL",
    ):
        resolve_dry_run(
            player_session,
            (),
            anchor_chunk_id=fixture["chunk_id"],
            window_chunks=30,
            epistemics_settings={},
            ambient_settings=_AMBIENT_SETTINGS,
            ambient_pacing_allowed=True,
        )


def test_context_building_features_established_protagonist(
    player_session: Session,
) -> None:
    """The real LORE character query always features the canonical player."""

    fixture = _seed_consumer_save(player_session, establish_protagonist=True)
    result = fetch_all_characters_with_references(
        player_session,
        [fixture["chunk_id"]],
        max_featured_characters=2,
    )

    player_character_id = fixture["characters"]["player"][0]
    assert canonical_player_character_id(player_session) == player_character_id
    dbapi_connection = player_session.connection().connection
    with dbapi_connection.cursor() as cur:
        assert canonical_player_character_id(cur) == player_character_id
    featured_by_id = {row["id"]: row for row in result["featured"]}
    assert featured_by_id[player_character_id]["reference_type"] == "user_character"


def test_context_building_rejects_save_without_protagonist(
    player_session: Session,
) -> None:
    """LORE context construction propagates the canonical loud failure."""

    fixture = _seed_consumer_save(player_session, establish_protagonist=False)

    with pytest.raises(
        PlayerIdentityNotEstablishedError,
        match="user_character is NULL",
    ):
        fetch_all_characters_with_references(
            player_session,
            [fixture["chunk_id"]],
            max_featured_characters=2,
        )


@pytest.mark.asyncio
async def test_async_gis_consumer_uses_same_identity_contract(
    disposable_player_db: tuple[str, Engine],
) -> None:
    """The asyncpg place-stub path resolves and rejects the same identity."""

    dbname, _engine = disposable_player_db
    conn = await asyncpg.connect(
        database=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        password=os.environ.get("PGPASSWORD"),
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5432")),
    )
    transaction = conn.transaction()
    await transaction.start()
    try:
        await conn.execute(
            "UPDATE global_variables "
            "SET user_character = NULL, base_timestamp = $1 "
            "WHERE id = true",
            _WORLD_TIME,
        )
        layer_id = int(
            await conn.fetchval(
                "INSERT INTO layers (name) VALUES ($1) RETURNING id",
                f"identity-layer-{uuid.uuid4().hex[:8]}",
            )
        )
        zone_id = int(
            await conn.fetchval(
                "INSERT INTO zones (name, layer) VALUES ($1, $2) RETURNING id",
                f"identity-zone-{uuid.uuid4().hex[:8]}",
                layer_id,
            )
        )
        place_entity_id = int(
            await conn.fetchval(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('place', true) RETURNING id"
            )
        )
        place_id = int(
            await conn.fetchval(
                "INSERT INTO places (name, type, zone, entity_id) "
                "VALUES ($1, 'fixed_location', $2, $3) RETURNING id",
                f"identity-async-place-{uuid.uuid4().hex[:8]}",
                zone_id,
                place_entity_id,
            )
        )
        character_entity_id = int(
            await conn.fetchval(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('character', true) RETURNING id"
            )
        )
        character_id = int(
            await conn.fetchval(
                "INSERT INTO characters (name, current_location, entity_id) "
                "VALUES ($1, $2, $3) RETURNING id",
                f"identity-async-player-{uuid.uuid4().hex[:8]}",
                place_id,
                character_entity_id,
            )
        )
        await conn.execute(
            "UPDATE global_variables SET user_character = $1 WHERE id = true",
            character_id,
        )

        assert await story_active_zone_async(conn) == zone_id

        await conn.execute(
            "UPDATE global_variables SET user_character = NULL WHERE id = true"
        )
        with pytest.raises(
            PlayerIdentityNotEstablishedError,
            match="user_character is NULL",
        ):
            await story_active_zone_async(conn)
    finally:
        await transaction.rollback()
        await conn.close()
