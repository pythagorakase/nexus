"""PostgreSQL coverage for canonical player-identity consumers.

The module clones ``NEXUS_template`` with the dump-based new-story helper,
then rolls each consumer fixture back inside that disposable database. No
save-slot or template database is mutated.
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Iterator

import asyncpg  # type: ignore[import-untyped]
import psycopg2  # type: ignore[import-untyped]
import pytest
from psycopg2 import sql  # type: ignore[import-untyped]
from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from nexus.agents.lore.logon_utility import read_user_character_id
from nexus.agents.lore.utils.entity_queries import (
    fetch_all_characters_with_references,
)
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.memnon.memnon import MEMNON
from nexus.agents.orrery.geo import story_active_zone, story_active_zone_async
from nexus.agents.orrery.player_identity import (
    PlayerIdentityNotEstablishedError,
    canonical_player_character_id,
)
from nexus.agents.orrery.resolver import _load_local_weather, resolve_dry_run
from nexus.agents.orrery.retrograde_persistence import (
    _load_persisted_protagonist_identity,
)
from nexus.api import db_pool, narrative, save_slots, slot_state, slot_utils
from nexus.api.narrative_generation import generate_bootstrap_narrative
from nexus.config.settings_models import OrreryWeatherSettings
from nexus.memory.manager import ContextMemoryManager
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


def _connect(dbname: str, *, dict_cursor: bool = False) -> Any:
    """Open a direct psycopg connection to the disposable database."""

    kwargs: dict[str, Any] = {
        "dbname": dbname,
        "user": os.environ.get("PGUSER", "pythagor"),
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
        "connect_timeout": 2,
    }
    if dict_cursor:
        kwargs["cursor_factory"] = RealDictCursor
    return psycopg2.connect(
        **kwargs,
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


@contextmanager
def _disposable_player_database(prefix: str) -> Iterator[tuple[str, Engine]]:
    """Create, yield, and drop one dump-cloned scratch database."""

    dbname = f"{prefix}_{uuid.uuid4().hex[:10]}"
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


@pytest.fixture(scope="module")
def disposable_player_db() -> Iterator[tuple[str, Engine]]:
    """Yield the shared rollback-only consumer database."""

    with _disposable_player_database("qa_player_identity") as database:
        yield database


@pytest.fixture()
def isolated_player_db() -> Iterator[tuple[str, Engine]]:
    """Yield an isolated clone for consumers that open their own connections."""

    with _disposable_player_database("qa_identity_surface") as database:
        yield database


@contextmanager
def _direct_connection(
    dbname: str,
    *,
    dict_cursor: bool = False,
) -> Iterator[Any]:
    """Match the production pool transaction contract against a scratch DB."""

    conn = _connect(dbname, dict_cursor=dict_cursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
    layer_id = int(
        session.execute(
            text(
                """
                INSERT INTO layers (name)
                VALUES (:name)
                RETURNING id
                """
            ),
            {"name": f"identity-layer-{uuid.uuid4().hex[:8]}"},
        ).scalar_one()
    )
    zone_id = int(
        session.execute(
            text(
                """
                INSERT INTO zones (name, layer)
                VALUES (:name, :layer_id)
                RETURNING id
                """
            ),
            {
                "name": f"identity-zone-{uuid.uuid4().hex[:8]}",
                "layer_id": layer_id,
            },
        ).scalar_one()
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
                INSERT INTO places (name, type, summary, zone, entity_id)
                VALUES (
                    :name, 'fixed_location', :summary, :zone_id, :entity_id
                )
                RETURNING id
                """
            ),
            {
                "name": f"identity-place-{uuid.uuid4().hex[:8]}",
                "summary": "Rollback-only canonical identity fixture.",
                "zone_id": zone_id,
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
            INSERT INTO chunk_metadata (
                chunk_id, season, episode, scene, world_layer,
                world_time, scene_weather
            ) VALUES (
                :chunk_id, 3, 4, 5, 'primary', :world_time, 'warm'
            )
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
        "place_id": place_id,
        "zone_id": zone_id,
    }


def _commit_consumer_save(
    engine: Engine,
    *,
    establish_protagonist: bool,
) -> dict[str, Any]:
    """Commit one consumer fixture for entry points that open connections."""

    with Session(engine) as session:
        fixture = _seed_consumer_save(
            session,
            establish_protagonist=establish_protagonist,
        )
        session.commit()
    return fixture


class _DatabaseMemnon:
    """Minimal established MEMNON boundary backed by a real database engine."""

    def __init__(self, engine: Engine) -> None:
        self.db_manager = SimpleNamespace(engine=engine)
        self.Session = sessionmaker(bind=engine)
        self.idf_dictionary = None


def _memnon_alias_reader(engine: Engine) -> MEMNON:
    """Build the smallest real MEMNON instance needed by ``_load_aliases``."""

    # MEMNON.__init__ initializes embedding models. The migrated fallback lives
    # entirely in _load_aliases, whose only runtime dependency is Session.
    memnon = MEMNON.__new__(MEMNON)
    memnon.Session = sessionmaker(bind=engine)
    return memnon


def _seed_soft_site_save(engine: Engine, state: str) -> dict[str, Any]:
    """Commit one lifecycle state for the three connection-owning soft sites."""

    with Session(engine) as session:
        chunk_count = int(
            session.execute(text("SELECT count(*) FROM narrative_chunks")).scalar_one()
        )
        incubator_count = int(
            session.execute(text("SELECT count(*) FROM incubator")).scalar_one()
        )
        if chunk_count != 0 or incubator_count != 0:
            raise RuntimeError(
                "Disposable template unexpectedly contains committed story rows"
            )
        result = session.execute(
            text(
                """
                UPDATE global_variables
                SET user_character = NULL,
                    setting = NULL,
                    base_timestamp = NULL
                WHERE id = true
                """
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("Disposable template lacks global_variables id=true")

        character_name: str | None = None
        if state == "established":
            session.execute(
                text(
                    """
                    UPDATE global_variables
                    SET setting = '{"world_name":"Identity Surface"}'::jsonb,
                        base_timestamp = :world_time
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
                        VALUES (
                            :name, 'fixed_location', :summary, :entity_id
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "name": f"soft-site-place-{uuid.uuid4().hex[:8]}",
                        "summary": "Committed soft-site identity fixture.",
                        "entity_id": place_entity_id,
                    },
                ).scalar_one()
            )
            character_id, _entity_id = _insert_character(
                session,
                label="soft-site-player",
                place_id=place_id,
            )
            character_name = str(
                session.execute(
                    text("SELECT name FROM characters WHERE id = :id"),
                    {"id": character_id},
                ).scalar_one()
            )
            session.execute(
                text(
                    """
                    UPDATE global_variables
                    SET user_character = :character_id
                    WHERE id = true
                    """
                ),
                {"character_id": character_id},
            )
        elif state == "post-marker-null":
            session.execute(
                text(
                    """
                    UPDATE global_variables
                    SET setting = '{"world_name":"Identity Marker"}'::jsonb
                    WHERE id = true
                    """
                )
            )
        elif state == "missing-global":
            session.execute(text("DELETE FROM global_variables WHERE id = true"))
        elif state != "empty":
            raise ValueError(f"Unknown soft-site fixture state: {state}")
        session.commit()
    return {"character_name": character_name}


def _route_soft_sites(monkeypatch: pytest.MonkeyPatch, scratch_dbname: str) -> None:
    """Route only database selection to a disposable clone."""

    # Identity helpers and all consumer SQL stay production-real; these seams
    # merely avoid touching save_01 through save_05.
    monkeypatch.setattr(
        narrative,
        "require_slot_dbname",
        lambda *, slot=None, dbname=None: scratch_dbname,
    )
    monkeypatch.setattr(slot_state, "slot_dbname", lambda _slot: scratch_dbname)
    monkeypatch.setattr(save_slots, "slot_dbname", lambda _slot: scratch_dbname)
    monkeypatch.setattr(slot_utils, "all_slots", lambda: (1,))
    monkeypatch.setattr(
        slot_state,
        "get_connection",
        lambda _dbname, dict_cursor=False: _direct_connection(
            scratch_dbname,
            dict_cursor=dict_cursor,
        ),
    )
    monkeypatch.setattr(
        save_slots,
        "get_connection",
        lambda _dbname, dict_cursor=False: _direct_connection(
            scratch_dbname,
            dict_cursor=dict_cursor,
        ),
    )


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


def test_turn_cycle_intertitle_uses_canonical_identity_for_both_states(
    player_session: Session,
) -> None:
    """The real intertitle loader resolves the player place or fails loudly."""

    fixture = _seed_consumer_save(player_session, establish_protagonist=True)
    intertitle = TurnCycleManager._load_intertitle(
        player_session,
        anchor_chunk_id=fixture["chunk_id"],
    )

    assert intertitle is not None
    assert intertitle["season"] == 3
    assert intertitle["episode"] == 4
    assert intertitle["scene"] == 5
    assert intertitle["world_layer"] == "primary"
    assert (
        datetime.fromisoformat(intertitle["world_time"]).astimezone(timezone.utc)
        == _WORLD_TIME
    )
    player_character_id = fixture["characters"]["player"][0]
    expected_place = player_session.execute(
        text("SELECT name FROM places WHERE id = :id"),
        {"id": fixture["place_id"]},
    ).scalar_one()
    assert intertitle["location_name"] == expected_place

    player_session.execute(
        text("UPDATE global_variables SET user_character = NULL WHERE id = true")
    )
    with pytest.raises(
        PlayerIdentityNotEstablishedError,
        match="user_character is NULL",
    ):
        TurnCycleManager._load_intertitle(
            player_session,
            anchor_chunk_id=fixture["chunk_id"],
        )
    assert player_character_id is not None


def test_logon_context_reader_uses_canonical_identity_for_both_states(
    isolated_player_db: tuple[str, Engine],
) -> None:
    """The real LOGON tag-exposure reader shares the loud contract."""

    dbname, engine = isolated_player_db
    fixture = _commit_consumer_save(engine, establish_protagonist=True)
    player_character_id = fixture["characters"]["player"][0]

    assert read_user_character_id(dbname) == player_character_id

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE global_variables SET user_character = NULL WHERE id = true")
        )
    with pytest.raises(
        PlayerIdentityNotEstablishedError,
        match="user_character is NULL",
    ):
        read_user_character_id(dbname)


def test_memnon_alias_reader_uses_canonical_pov_and_never_falls_back(
    isolated_player_db: tuple[str, Engine],
) -> None:
    """Canonical failure exits MEMNON before its legacy alias fallback."""

    _dbname, engine = isolated_player_db
    fixture = _commit_consumer_save(engine, establish_protagonist=True)
    player_character_id = fixture["characters"]["player"][0]
    with engine.connect() as connection:
        player_name = str(
            connection.execute(
                text("SELECT name FROM characters WHERE id = :id"),
                {"id": player_character_id},
            ).scalar_one()
        )
    memnon = _memnon_alias_reader(engine)

    aliases = memnon._load_aliases()

    assert aliases[player_name.lower()][0]
    assert {"You", "Your", "Yours", "Yourself"}.issubset(aliases[player_name.lower()])

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE global_variables SET user_character = NULL WHERE id = true")
        )
    with pytest.raises(
        PlayerIdentityNotEstablishedError,
        match="user_character is NULL",
    ):
        memnon._load_aliases()


def test_resolver_local_weather_uses_canonical_identity_for_both_states(
    player_session: Session,
) -> None:
    """The smallest real local-weather loader resolves the canonical place."""

    fixture = _seed_consumer_save(player_session, establish_protagonist=True)
    player_entity_id = fixture["characters"]["player"][1]
    settings = OrreryWeatherSettings(enabled=True).model_dump()

    anchor_weather, place_weather = _load_local_weather(
        player_session,
        anchor_chunk_id=fixture["chunk_id"],
        world_time=_WORLD_TIME,
        locations={player_entity_id: fixture["place_id"]},
        location_zones={fixture["place_id"]: fixture["zone_id"]},
        weather_settings=settings,
    )

    assert anchor_weather == "warm"
    assert place_weather[fixture["place_id"]] == "warm"

    player_session.execute(
        text("UPDATE global_variables SET user_character = NULL WHERE id = true")
    )
    with pytest.raises(
        PlayerIdentityNotEstablishedError,
        match="user_character is NULL",
    ):
        _load_local_weather(
            player_session,
            anchor_chunk_id=fixture["chunk_id"],
            world_time=_WORLD_TIME,
            locations={player_entity_id: fixture["place_id"]},
            location_zones={fixture["place_id"]: fixture["zone_id"]},
            weather_settings=settings,
        )


def test_sync_gis_reader_uses_canonical_identity_for_both_states(
    player_session: Session,
) -> None:
    """The psycopg GIS reader resolves the same player identity contract."""

    fixture = _seed_consumer_save(player_session, establish_protagonist=True)
    dbapi_connection = player_session.connection().connection
    with dbapi_connection.cursor() as cur:
        assert story_active_zone(cur) == fixture["zone_id"]

    player_session.execute(
        text("UPDATE global_variables SET user_character = NULL WHERE id = true")
    )
    with dbapi_connection.cursor() as cur:
        with pytest.raises(
            PlayerIdentityNotEstablishedError,
            match="user_character is NULL",
        ):
            story_active_zone(cur)


def test_retrograde_protagonist_reader_uses_canonical_identity_for_both_states(
    player_session: Session,
) -> None:
    """The real persisted-protagonist loader resolves aliases or fails loudly."""

    fixture = _seed_consumer_save(player_session, establish_protagonist=True)
    player_character_id = fixture["characters"]["player"][0]
    dbapi_connection = player_session.connection().connection
    with dbapi_connection.cursor() as cur:
        identity = _load_persisted_protagonist_identity(cur)

    assert identity.character_id == player_character_id
    assert identity.name.startswith("identity-player-")

    player_session.execute(
        text("UPDATE global_variables SET user_character = NULL WHERE id = true")
    )
    with dbapi_connection.cursor() as cur:
        with pytest.raises(
            PlayerIdentityNotEstablishedError,
            match="user_character is NULL",
        ):
            _load_persisted_protagonist_identity(cur)


def test_memory_manager_metadata_uses_canonical_identity_for_both_states(
    isolated_player_db: tuple[str, Engine],
) -> None:
    """The real metadata initializer maps POV aliases and rejects NULL identity."""

    _dbname, engine = isolated_player_db
    fixture = _commit_consumer_save(engine, establish_protagonist=True)
    player_character_id = fixture["characters"]["player"][0]
    with engine.connect() as connection:
        player_name = str(
            connection.execute(
                text("SELECT name FROM characters WHERE id = :id"),
                {"id": player_character_id},
            ).scalar_one()
        )

    # Constructing the full MEMNON embedding stack is unrelated to this path;
    # ContextMemoryManager._initialize_entity_maps needs only its real engine.
    manager = ContextMemoryManager({}, memnon=_DatabaseMemnon(engine))

    assert manager.user_character_name == player_name
    assert manager.alias_inverse["you"] == player_name.lower()

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE global_variables SET user_character = NULL WHERE id = true")
        )
    with pytest.raises(
        PlayerIdentityNotEstablishedError,
        match="user_character is NULL",
    ):
        ContextMemoryManager({}, memnon=_DatabaseMemnon(engine))


class _BootstrapProviderBoundaryReached(Exception):
    """Sentinel raised after bootstrap DB context and before provider setup."""


@pytest.mark.asyncio
async def test_bootstrap_identity_and_location_use_canonical_player_for_both_states(
    player_session: Session,
) -> None:
    """The real bootstrap entry reads identity/location before provider setup."""

    fixture = _seed_consumer_save(player_session, establish_protagonist=True)
    dbapi_connection = player_session.connection().connection

    def stop_at_provider_boundary() -> Any:
        # The injected settings seam is reached only after the production entry
        # has resolved the real canonical character and starting-location rows.
        raise _BootstrapProviderBoundaryReached

    with pytest.raises(_BootstrapProviderBoundaryReached):
        await generate_bootstrap_narrative(
            dbapi_connection,
            "identity-bootstrap",
            "Begin.",
            slot=1,
            load_settings=stop_at_provider_boundary,
        )

    player_session.execute(
        text("UPDATE global_variables SET user_character = NULL WHERE id = true")
    )
    with pytest.raises(
        PlayerIdentityNotEstablishedError,
        match="user_character is NULL",
    ):
        await generate_bootstrap_narrative(
            dbapi_connection,
            "identity-bootstrap-missing",
            "Begin.",
            slot=1,
            load_settings=stop_at_provider_boundary,
        )
    assert fixture["place_id"] is not None


@pytest.mark.asyncio
async def test_soft_sites_resolve_an_established_protagonist(
    isolated_player_db: tuple[str, Engine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All three production soft entries return established player state."""

    dbname, engine = isolated_player_db
    fixture = _seed_soft_site_save(engine, "established")
    _route_soft_sites(monkeypatch, dbname)

    user_character = await narrative.get_user_character(slot=1)
    slot_metadata = save_slots.list_slots()
    lifecycle = slot_state.get_slot_state(1)

    assert user_character == {"name": fixture["character_name"]}
    assert slot_metadata[0]["character_name"] == fixture["character_name"]
    assert lifecycle.narrative_state is not None
    assert lifecycle.is_empty is False


@pytest.mark.asyncio
async def test_soft_sites_accept_only_a_truly_empty_pre_protagonist_slot(
    isolated_player_db: tuple[str, Engine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NULL remains soft only before every committed story marker."""

    dbname, engine = isolated_player_db
    _seed_soft_site_save(engine, "empty")
    _route_soft_sites(monkeypatch, dbname)

    user_character = await narrative.get_user_character(slot=1)
    slot_metadata = save_slots.list_slots()
    lifecycle = slot_state.get_slot_state(1)

    assert user_character == {"name": None}
    assert slot_metadata[0]["character_name"] is None
    assert lifecycle.narrative_state is None
    assert lifecycle.is_empty or lifecycle.is_wizard_mode


@pytest.mark.asyncio
async def test_soft_sites_reject_null_protagonist_after_story_marker(
    isolated_player_db: tuple[str, Engine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed marker converts NULL identity into loud corruption."""

    dbname, engine = isolated_player_db
    _seed_soft_site_save(engine, "post-marker-null")
    _route_soft_sites(monkeypatch, dbname)

    with pytest.raises(PlayerIdentityNotEstablishedError):
        await narrative.get_user_character(slot=1)
    with pytest.raises(PlayerIdentityNotEstablishedError):
        save_slots.list_slots()
    with pytest.raises(PlayerIdentityNotEstablishedError):
        slot_state.get_slot_state(1)


@pytest.mark.asyncio
async def test_soft_sites_do_not_catch_generic_runtime_error(
    isolated_player_db: tuple[str, Engine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only PlayerIdentityNotEstablishedError receives lifecycle softening."""

    dbname, engine = isolated_player_db
    _seed_soft_site_save(engine, "missing-global")
    _route_soft_sites(monkeypatch, dbname)

    with pytest.raises(RuntimeError) as user_error:
        await narrative.get_user_character(slot=1)
    assert type(user_error.value) is RuntimeError

    with pytest.raises(RuntimeError) as metadata_error:
        save_slots.list_slots()
    assert type(metadata_error.value) is RuntimeError

    with pytest.raises(RuntimeError) as lifecycle_error:
        slot_state.get_slot_state(1)
    assert type(lifecycle_error.value) is RuntimeError


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
