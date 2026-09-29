"""Shared PostgreSQL helpers for disposable integration-test databases.

Every helper resolves its server through ``nexus.database``, the same contract
the runtime uses: explicit ``[api.database]`` values, then the PG* environment,
then libpq's Unix socket and the operating-system user. Fixtures that seed a
database therefore reach the server that the code under test reads.

Tests reach PostgreSQL only through these helpers (``connect``,
``asyncpg_kwargs``, ``sqlalchemy_url``, and ``subprocess_env`` for command-line
tools), through ``nexus.database`` itself (``connection_kwargs``, and
``database_url`` where a URL string is needed), or, for a save slot, through
``nexus.api.slot_utils.get_slot_db_url``. The offline guard in
``tests/test_pg_target_contract.py`` fails the default gate on any test that
reads PG* directly, spells a PostgreSQL URL naming a server, or hands a driver
(however imported or aliased) a target that is not a direct helper call or a
name bound once to one in the same function: spelled host, port, user, or
database keywords, a positional DSN or URL, an expanded mapping, or no target
at all.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from typing import Any

import psycopg2
from psycopg2 import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url

from nexus.api import db_pool
from nexus.config.story_model import StorySettings, write_story_settings
from nexus.database import (
    asyncpg_kwargs as contract_asyncpg_kwargs,
    connection_kwargs,
    create_slot_engine,
    database_url,
    subprocess_env,
)
from scripts import migrate, new_story_setup


def connection_parameters(dbname: str) -> dict[str, Any]:
    """Return the runtime contract's psycopg2 keyword parameters for ``dbname``.

    Host, port, user, password, connect timeout, and session options all come
    from ``nexus.database.connection_kwargs``; only the database name is the
    caller's. Keyword parameters survive Unix-socket directories and IPv6
    hosts that break naive URI interpolation.
    """

    return connection_kwargs(dbname)


def connect(dbname: str, *, cursor_factory: Any = None) -> Any:
    """Open a direct psycopg2 connection to ``dbname`` on the contract's server."""

    kwargs = connection_parameters(dbname)
    if cursor_factory is not None:
        kwargs["cursor_factory"] = cursor_factory
    return psycopg2.connect(**kwargs)


def asyncpg_kwargs(dbname: str) -> dict[str, Any]:
    """Return the contract's ``asyncpg.connect`` keyword arguments for ``dbname``."""

    return contract_asyncpg_kwargs(dbname)


def sqlalchemy_url(dbname: str) -> URL:
    """Return the contract's URL for ``dbname`` as a SQLAlchemy ``URL``.

    Pass the object to SQLAlchemy directly. A string for libpq or a command
    line comes from ``nexus.database.database_url``: SQLAlchemy renders spaces
    in query values as ``+``, which libpq does not decode.
    """

    return make_url(database_url(dbname))


_connect = connect

_TARGET_IDENTITY_SQL = (
    "SELECT current_database(), current_setting('port'), "
    "(pg_postmaster_start_time() AT TIME ZONE 'UTC')::text"
)


def assert_one_target(dbname: str) -> None:
    """Fail unless fixture, runtime, and URL clients reach one database.

    Fixtures seed through ``connect``, while production code resolves
    ``nexus.database`` directly or through ``database_url``. Both derive from
    ``connection_kwargs``, so this guards against drift: a fixture that grows
    its own resolver would seed one server while the code under test queries
    another (issue #804). The server's listening port and postmaster start time
    identify the instance whether a client arrives over TCP or a Unix socket.

    The pooled client checked here is the ``create_slot_engine`` SQLAlchemy
    engine built from ``database_url``. ``db_pool`` accepts only ``save_0N``
    names, so it is not checked out; its parameters come from the same
    ``connection_kwargs`` call that is checked.
    """

    identities: dict[str, tuple[Any, ...]] = {}
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(_TARGET_IDENTITY_SQL)
        identities["tests.pg_fixtures.connect"] = tuple(cur.fetchone())
    with closing(psycopg2.connect(**connection_kwargs(dbname))) as conn:
        with conn.cursor() as cur:
            cur.execute(_TARGET_IDENTITY_SQL)
            identities["nexus.database.connection_kwargs"] = tuple(cur.fetchone())
    engine = create_slot_engine(database_url(dbname))
    try:
        with engine.connect() as sa_conn:
            row = sa_conn.execute(text(_TARGET_IDENTITY_SQL)).one()
            identities["nexus.database.database_url"] = tuple(row)
    finally:
        engine.dispose()
    if len(set(identities.values())) != 1 or any(
        identity[0] != dbname for identity in identities.values()
    ):
        raise AssertionError(
            f"PostgreSQL clients disagree on the {dbname!r} target: {identities!r}"
        )


@contextmanager
def disposable_slot_database(
    prefix: str,
    *,
    source_db: str = "NEXUS_template",
    include_data: bool = False,
    story_pin: str | None = "TEST",
) -> Iterator[str]:
    """Yield a uniquely named template clone and always remove it afterward.

    ``include_data`` snapshots a source corpus with pg_dump, restores it into
    the disposable target, and migrates only that clone. It never disconnects,
    unlocks, or changes the source database. Default cloning copies seed data
    only, suitable for tests that create their own stories. Clones are pinned
    to TEST before corpus migrations so backfilled work is also safe. Preserving
    the source pin requires the explicit live-LLM opt-in.

    Fails loudly when the admin connection is unavailable; opting into the
    PostgreSQL gate means PostgreSQL is required.
    """

    if story_pin is None and os.environ.get("NEXUS_RUN_LIVE_LLM") != "1":
        raise ValueError("story_pin=None requires NEXUS_RUN_LIVE_LLM=1")
    # The clone is created and migrated by scripts that resolve nexus.database
    # themselves, and dropped through the admin connection below. Prove both
    # still reach one server before creating anything, so a clone cannot
    # outlive its fixture.
    assert_one_target("postgres")

    def pin_clone() -> None:
        if story_pin is not None:
            with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
                write_story_settings(
                    cur, StorySettings(skald_model=story_pin, gaia_model=None)
                )

    dbname = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin: Any = None
    original_use_pool = new_story_setup.USE_POOL
    try:
        db_pool.dispose_database(dbname)
        # NEXUS_RUN_POSTGRES=1 asserts PostgreSQL is required: an unreachable
        # or misconfigured server is a failure, never a skip (a skipped gate is
        # how issue #735's debt hid for two months). The requires_postgres
        # marker already skips when the gate is not opted in.
        admin = _connect("postgres")
        admin.autocommit = True
        new_story_setup.USE_POOL = False
        if include_data:
            with admin.cursor() as cur:
                cur.execute(
                    sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                        sql.Identifier(dbname)
                    )
                )
            with tempfile.TemporaryDirectory(prefix="nexus-pg-corpus-") as archive_dir:
                archive_path = os.path.join(archive_dir, "corpus.dump")
                # subprocess_env() carries the contract's target, password, and
                # session options, keeping the password off the command line.
                subprocess.run(
                    [
                        "pg_dump",
                        "--format=custom",
                        "--file",
                        archive_path,
                        "--dbname",
                        source_db,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    env=subprocess_env(),
                )
                subprocess.run(
                    [
                        "pg_restore",
                        "--exit-on-error",
                        "--no-owner",
                        "--no-acl",
                        "--dbname",
                        dbname,
                        archive_path,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    env=subprocess_env(),
                )
            pin_clone()
            _, failed = migrate.migrate_database(dbname, skip_locked=False)
            if failed:
                raise RuntimeError(
                    f"Corpus clone {dbname} has {failed} failed migrations"
                )
        else:
            new_story_setup.initialize_slot_database(dbname, source_db=source_db)
            pin_clone()
        db_pool.dispose_database(dbname)
        yield dbname
    finally:
        new_story_setup.USE_POOL = original_use_pool
        try:
            db_pool.dispose_database(dbname)
        finally:
            if admin is not None:
                try:
                    with admin.cursor() as cur:
                        try:
                            cur.execute(
                                "SELECT pg_terminate_backend(pid) "
                                "FROM pg_stat_activity "
                                "WHERE datname = %s AND pid <> pg_backend_pid()",
                                (dbname,),
                            )
                        finally:
                            cur.execute(
                                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                                    sql.Identifier(dbname)
                                )
                            )
                finally:
                    admin.close()


@contextmanager
def disposable_database(prefix: str) -> Iterator[str]:
    """Yield a uniquely named empty database and always remove it afterward.

    The database is created from ``template0`` with no schema, seed rows, or
    migration stamps, for tests that exercise restore and runner mechanics on
    a bare target. Teardown re-allows connections (a test may have closed
    them), terminates remaining sessions, and drops the database.
    """

    assert_one_target("postgres")
    dbname = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin = _connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(dbname)
                )
            )
        yield dbname
    finally:
        try:
            db_pool.dispose_database(dbname)
            with admin.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
                if cur.fetchone() is not None:
                    cur.execute(
                        sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(
                            sql.Identifier(dbname)
                        )
                    )
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (dbname,),
                    )
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
        finally:
            admin.close()


def seed_protagonist(
    dbname: str,
    *,
    name: str = "Fixture Player",
    summary: str = "Canonical player for PostgreSQL coverage.",
    base_timestamp: str = "2100-01-01T00:00:00+00:00",
    current_location: int | None = None,
) -> tuple[int, int]:
    """Bind a fixture-owned player to the save and return character/entity IDs.

    Sets ``global_variables.base_timestamp`` before the character insert, which
    satisfies the need-clock anchor (migration 100); ``seed_story_clock`` can
    then add a head chunk after it. Refuses to move a clock that is already
    set (for example by ``seed_story_clock``): resetting ``base_timestamp``
    under stored chunks would desynchronize their ``world_time`` from the
    summed deltas until the next ``chunk_metadata`` write re-stamps them.
    """

    with closing(_connect(dbname)) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT base_timestamp FROM global_variables WHERE id = true")
            row = cur.fetchone()
            assert row is not None, f"{dbname} has no global_variables row"
            cur.execute("SELECT %s::timestamptz", (base_timestamp,))
            requested = cur.fetchone()[0]
            assert row[0] is None or row[0] == requested, (
                f"seed_protagonist would reset base_timestamp from {row[0]} to "
                f"{requested}; run it before seed_story_clock, or pass the "
                "clock already set"
            )
            cur.execute(
                "UPDATE global_variables SET base_timestamp = %s WHERE id = true",
                (base_timestamp,),
            )
            assert cur.rowcount == 1
            cur.execute(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('character', true) RETURNING id"
            )
            entity_id = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO characters (name, summary, entity_id, current_location)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (name, summary, entity_id, current_location),
            )
            character_id = int(cur.fetchone()[0])
            cur.execute(
                "UPDATE global_variables SET user_character = %s WHERE id = true",
                (character_id,),
            )
            assert cur.rowcount == 1
    return character_id, entity_id


def seed_committed_chunk(
    dbname: str,
    *,
    raw_text: str,
    season: int = 1,
    episode: int = 1,
    scene: int = 1,
    time_delta: timedelta = timedelta(minutes=1),
) -> int:
    """Insert one committed chunk with its primary-layer metadata; return its ID.

    ``time_delta`` is the story time elapsing during the chunk. The
    statement-level ``trg_chunk_metadata_refresh_world_time`` trigger stamps
    ``chunk_metadata.world_time`` as ``base_timestamp`` plus the cumulative
    deltas, so the chunk's clock is exact only once ``base_timestamp`` is set.

    The chunk carries no ``authorial_directives``, so it satisfies
    ``playable_narrative_predicate`` (reconstruction.py) and counts toward the
    playable ordinal and head-chunk reads.
    """

    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
            "VALUES (%s, %s) RETURNING id",
            (raw_text, raw_text),
        )
        chunk_id = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO chunk_metadata (
                chunk_id, season, episode, scene, world_layer,
                time_delta, generation_date, slug
            ) VALUES (
                %s, %s, %s, %s, 'primary', %s, now(), %s
            )
            """,
            (
                chunk_id,
                season,
                episode,
                scene,
                time_delta,
                f"S{season:02d}E{episode:02d}_{scene:03d}",
            ),
        )
        assert cur.rowcount == 1
    return chunk_id


def _require_need_clock_anchor(cur: Any, helper: str) -> None:
    """Fail by name when the save has no clock for the need-state trigger."""

    cur.execute(
        """
        SELECT COALESCE(
            (SELECT max(world_time) FROM chunk_metadata),
            (SELECT base_timestamp FROM global_variables WHERE id = true)
        )
        """
    )
    anchor = cur.fetchone()[0]
    assert anchor is not None, (
        f"{helper} needs a need-clock anchor: call seed_story_clock or "
        "seed_protagonist before seeding characters (migration 100 refuses "
        "to anchor need clocks to wall time)"
    )


def seed_story_clock(
    dbname: str,
    *,
    world_time: datetime,
    raw_text: str = "Fixture story clock.",
    season: int = 1,
    episode: int = 1,
    scene: int = 1,
) -> int:
    """Advance the canonical story clock to ``world_time`` with one chunk.

    Satisfies the need-clock anchor: migration 100's
    ``orrery_sync_character_need_states`` anchors every character's need
    clock at ``MAX(chunk_metadata.world_time)``, then at
    ``global_variables.base_timestamp``, and raises when both are NULL. It
    also gives the save a head chunk, which replay, checkpoint, and resolver
    reads anchor on.

    When the save has no ``base_timestamp`` yet, ``world_time`` becomes the
    bootstrap clock and the chunk elapses no time. Otherwise the chunk's
    ``time_delta`` is the gap from the current head clock, which must not be
    later than ``world_time``. The chunk is inserted through
    ``seed_committed_chunk``; the stored ``world_time`` is asserted exact and
    the chunk ID returned.
    """

    if world_time.tzinfo is None:
        raise ValueError("seed_story_clock needs a timezone-aware world_time")
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT base_timestamp FROM global_variables WHERE id = true")
        row = cur.fetchone()
        assert row is not None, f"{dbname} has no global_variables row"
        if row[0] is None:
            cur.execute(
                "UPDATE global_variables SET base_timestamp = %s WHERE id = true",
                (world_time,),
            )
            assert cur.rowcount == 1
        cur.execute(
            """
            SELECT gv.base_timestamp + COALESCE(
                (SELECT sum(COALESCE(time_delta, interval '0'))
                 FROM chunk_metadata),
                interval '0'
            )
            FROM global_variables gv
            WHERE gv.id = true
            """
        )
        head_clock = cur.fetchone()[0]
    time_delta = world_time - head_clock
    assert time_delta >= timedelta(0), (
        f"seed_story_clock cannot move the clock backward from {head_clock} "
        f"to {world_time}"
    )
    chunk_id = seed_committed_chunk(
        dbname,
        raw_text=raw_text,
        season=season,
        episode=episode,
        scene=scene,
        time_delta=time_delta,
    )
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT world_time FROM chunk_metadata WHERE chunk_id = %s",
            (chunk_id,),
        )
        stamped = cur.fetchone()
    assert (
        stamped is not None and stamped[0] == world_time
    ), f"seed_story_clock stamped {stamped!r}, expected {world_time}"
    return chunk_id


def seed_place(
    dbname: str,
    *,
    name: str,
    summary: str = "Fixture place.",
    longitude: float = -73.9857,
    latitude: float = 40.7484,
    place_type: str = "fixed_location",
) -> tuple[int, int]:
    """Insert one located place; return its place and entity IDs.

    The row takes the production insert shape (``db_converters``): the
    subtype trigger mints the ``place`` entity, and the point is a
    ``PointZM`` geography, so the place is on the map and a character's
    ``current_location`` or a travel payload can reference it.
    """

    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO places (name, type, summary, coordinates)
            VALUES (
                %s, %s::place_type, %s,
                ST_SetSRID(ST_MakePoint(%s, %s, 0, 0), 4326)::geography
            )
            RETURNING id, entity_id
            """,
            (name, place_type, summary, longitude, latitude),
        )
        row = cur.fetchone()
        assert row is not None and cur.rowcount == 1
    return int(row[0]), int(row[1])


def seed_character(
    dbname: str,
    *,
    name: str,
    summary: str = "Fixture character.",
    current_location: int | None = None,
    current_activity: str | None = None,
) -> tuple[int, int]:
    """Insert one active character; return its character and entity IDs.

    The row takes the production insert shape: the subtype trigger mints the
    ``character`` entity and the need-state trigger seeds its need rows. That
    trigger needs the need-clock anchor, so the save must already carry
    ``seed_story_clock`` or ``seed_protagonist``; a clockless save fails here
    by name rather than inside the trigger.
    """

    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        _require_need_clock_anchor(cur, "seed_character")
        cur.execute(
            """
            INSERT INTO characters (
                name, summary, current_location, current_activity
            ) VALUES (%s, %s, %s, %s)
            RETURNING id, entity_id
            """,
            (name, summary, current_location, current_activity),
        )
        row = cur.fetchone()
        assert row is not None and cur.rowcount == 1
        character_id, entity_id = int(row[0]), int(row[1])
        cur.execute(
            "SELECT count(*) FROM character_need_states "
            "WHERE character_entity_id = %s",
            (entity_id,),
        )
        assert cur.fetchone()[0] > 0, "the need-state trigger seeded no need rows"
    return character_id, entity_id


def seed_faction(
    dbname: str,
    *,
    name: str,
    summary: str = "Fixture faction.",
) -> tuple[int, int]:
    """Insert one active faction; return its faction and entity IDs.

    ``factions.id`` has no default, so the ID is allocated the way the
    production writers do (``MAX(id) + 1`` under a table lock), and the
    subtype trigger mints the ``faction`` entity.
    """

    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("LOCK TABLE factions IN SHARE ROW EXCLUSIVE MODE")
        cur.execute(
            """
            INSERT INTO factions (id, name, summary)
            SELECT COALESCE(max(id), 0) + 1, %s, %s FROM factions
            RETURNING id, entity_id
            """,
            (name, summary),
        )
        row = cur.fetchone()
        assert row is not None and cur.rowcount == 1
    return int(row[0]), int(row[1])


def seed_relationship(
    dbname: str,
    *,
    subject_character_id: int,
    object_character_id: int,
    relationship_type: str,
    emotional_valence: str = "+3|trusting",
    dynamic: str = "Fixture relationship.",
    recent_events: str = "None.",
    history: str = "Seeded for PostgreSQL coverage.",
    extra_data: Mapping[str, Any] | None = None,
) -> tuple[int, int]:
    """Insert one directed character relationship; return its key.

    ``character_relationships`` has no surrogate ID: its primary key is the
    ``(character1_id, character2_id)`` pair returned here. The row takes the
    trait compiler's production insert shape; ``valence_current`` is derived
    by ``trg_character_relationships_valence_boundary``. Migration 115's
    provenance trigger refuses any write without a transaction-local
    ``nexus.write_producer``, so the insert is attributed to ``manual``.
    """

    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SET LOCAL nexus.write_producer = 'manual'")
        cur.execute(
            """
            INSERT INTO character_relationships (
                character1_id, character2_id, relationship_type,
                emotional_valence, dynamic, recent_events, history, extra_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING character1_id, character2_id
            """,
            (
                subject_character_id,
                object_character_id,
                relationship_type,
                emotional_valence,
                dynamic,
                recent_events,
                history,
                json.dumps(dict(extra_data or {})),
            ),
        )
        row = cur.fetchone()
        assert row is not None and cur.rowcount == 1
    return int(row[0]), int(row[1])


def seed_entity_tag(
    dbname: str,
    *,
    entity_id: int,
    tag: str,
    source_kind: str = "template",
) -> int:
    """Bestow one active, registered tag on an entity; return the row ID.

    ``tag`` must be a non-deprecated tag from the template's seeded vocabulary;
    an unknown or deprecated tag fails the row-count assertion. The row is
    active (``cleared_at`` NULL), so checkpoints and ``entity_tags_current`` see
    it. A tag on a character entity fires the need-applicability sync (migration
    100), so the save needs the need-clock anchor first (``seed_story_clock`` or
    ``seed_protagonist``).
    """

    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_tags (entity_id, tag_id, source_kind)
            SELECT %s, t.id, %s
            FROM tags t
            WHERE t.tag = %s AND NOT t.deprecated
            RETURNING id
            """,
            (entity_id, source_kind, tag),
        )
        row = cur.fetchone()
        assert row is not None and cur.rowcount == 1, f"tag {tag!r} is not seeded"
    return int(row[0])
