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

Seed helpers write only disposable databases: each calls
``require_disposable_target`` before it connects, which refuses the owner's
save slots and ``NEXUS_template`` by name.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from typing import Any

import psycopg2
from psycopg2 import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url

from nexus.agents.orrery.geo import resolve_zone_for_point
from nexus.api import db_pool
from nexus.api.slot_utils import all_slots, slot_dbname
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


# Derived once, at import, from the slot contract. Fixtures such as
# ``offline_gate_db`` monkeypatch ``slot_utils.slot_dbname`` to return their
# clone while a test runs; resolving the owner names through that attribute at
# call time would refuse the clone and admit the owner's database.
_OWNER_DATABASES = frozenset(
    {"NEXUS_template", *(slot_dbname(slot) for slot in all_slots())}
)


def require_disposable_target(dbname: str) -> str:
    """Return ``dbname`` unless it names an owner database, which raises.

    The owner databases are ``NEXUS_template`` and every save slot that
    ``nexus.api.slot_utils`` defines (``save_01`` through ``save_05``). A seed
    aimed at one is always a test bug, so there is no override or allowlist:
    every seed helper calls this before it opens a connection, and tests seed
    only clones from ``disposable_slot_database`` or ``disposable_database``.
    """

    if dbname in _OWNER_DATABASES:
        raise RuntimeError(
            f"Refusing to seed owner database {dbname!r}: seed helpers write "
            "only disposable clones from disposable_slot_database"
        )
    return dbname


# The unrouted slot resolver, captured at import under a name the routing
# sweep below never rebinds.
_UNROUTED_SLOT_DBNAME = slot_dbname


def route_slot_to_disposable(
    patch: Callable[[Any, str, Any], None], *, slot: int, dbname: str
) -> None:
    """Route one slot number to a disposable clone in every loaded module.

    Production code resolves a slot's database through
    ``nexus.api.slot_utils.slot_dbname``, either through the module attribute
    (``require_slot_dbname``, ``get_slot_db_url``, ``connection_kwargs`` and
    every function-local import) or through a name bound at import
    (``from nexus.api.slot_utils import slot_dbname``). ``patch`` rebinds the
    module attribute and every loaded module's bound name to a resolver that
    returns ``dbname`` for ``slot`` and raises for any other slot, and
    narrows ``VALID_DBNAMES`` to the clone, so a path this sweep missed fails
    loudly instead of reaching an owner database. Modules imported afterward
    bind the routed resolver.

    ``patch`` is ``monkeypatch.setattr`` inside a test (undone at teardown) or
    the builtin ``setattr`` in a child process that serves the gateway for
    the clone (``tests.slot_routed_gateway``). The caller sets ``NEXUS_SLOT``
    when the code under test resolves the active slot.
    """

    from nexus.api import slot_utils

    require_disposable_target(dbname)

    def routed_slot_dbname(slot_number: int) -> str:
        if slot_number != slot:
            raise RuntimeError(
                f"Slot {slot_number} is not routed: only slot {slot} reaches "
                f"the disposable clone {dbname!r}"
            )
        return dbname

    patch(slot_utils, "VALID_DBNAMES", {dbname})
    patch(slot_utils, "slot_dbname", routed_slot_dbname)
    for name, module in list(sys.modules.items()):
        if module is None or not name.startswith(("nexus.", "scripts.", "tests.")):
            continue
        if vars(module).get("slot_dbname") is _UNROUTED_SLOT_DBNAME:
            patch(module, "slot_dbname", routed_slot_dbname)


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

    When the clock is first set under chunks that already exist, those chunks
    carry wall-clock ``world_time`` stamps (the refresh trigger falls back to
    ``now()`` while ``base_timestamp`` is NULL). The helper re-stamps them
    through the ``UPDATE OF time_delta`` statement trigger and asserts the
    head clock is ``base_timestamp`` plus the summed deltas before the
    character insert, so need clocks never anchor to wall time (#640/#645).
    """

    require_disposable_target(dbname)
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
            if row[0] is None:
                cur.execute("UPDATE chunk_metadata SET time_delta = time_delta")
            _require_need_clock_anchor(cur, "seed_protagonist")
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

    require_disposable_target(dbname)
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
    """Fail by name when the save has no exact story clock for need rows.

    ``orrery_sync_character_need_states`` anchors need clocks at
    ``MAX(chunk_metadata.world_time)``, then at ``base_timestamp``. The anchor
    is exact only when ``base_timestamp`` is set and, if chunks exist, the head
    ``world_time`` equals ``base_timestamp`` plus the summed deltas. Chunks
    stamped while ``base_timestamp`` was NULL carry wall-clock ``world_time``
    and fail here rather than seeding wall-clock need clocks.
    """

    cur.execute(
        """
        SELECT
            gv.base_timestamp,
            (SELECT count(*) FROM chunk_metadata),
            (SELECT max(world_time) FROM chunk_metadata),
            gv.base_timestamp + COALESCE(
                (SELECT sum(COALESCE(time_delta, interval '0'))
                 FROM chunk_metadata),
                interval '0'
            )
        FROM global_variables gv
        WHERE gv.id = true
        """
    )
    row = cur.fetchone()
    assert row is not None, f"{helper}: the save has no global_variables row"
    base_timestamp, chunk_count, head_world_time, expected_head = row
    assert base_timestamp is not None, (
        f"{helper} needs a need-clock anchor: call seed_story_clock or "
        "seed_protagonist before seeding characters (migration 100 refuses "
        "to anchor need clocks to wall time)"
    )
    assert chunk_count == 0 or head_world_time == expected_head, (
        f"{helper} found a wall-clock need-clock anchor: head world_time "
        f"{head_world_time} is not base_timestamp {base_timestamp} plus the "
        f"summed deltas ({expected_head}); re-stamp chunk_metadata after "
        "setting base_timestamp"
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

    require_disposable_target(dbname)
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


def seed_zone(
    dbname: str,
    *,
    name: str,
    min_longitude: float,
    min_latitude: float,
    max_longitude: float,
    max_latitude: float,
    summary: str = "Fixture zone.",
) -> int:
    """Insert one bounded zone under its own layer; return the zone ID.

    Production place writers resolve every place's ``zone`` through
    ``nexus.agents.orrery.geo`` and raise when no zone has a boundary, so a
    save needs a bounded zone before ``seed_place``. The boundary is the
    envelope of the given corners as a ``MultiPolygon`` in SRID 4326, and the
    layer row mirrors the new-story mapper's ``layers`` insert.
    """

    require_disposable_target(dbname)
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO layers (name, type, description) "
            "VALUES (%s, 'planet', %s) RETURNING id",
            (f"{name} Layer", summary),
        )
        layer_row = cur.fetchone()
        assert layer_row is not None and cur.rowcount == 1
        cur.execute(
            """
            INSERT INTO zones (name, summary, boundary, layer)
            VALUES (
                %s, %s,
                ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 4326)),
                %s
            )
            RETURNING id
            """,
            (
                name,
                summary,
                min_longitude,
                min_latitude,
                max_longitude,
                max_latitude,
                layer_row[0],
            ),
        )
        row = cur.fetchone()
        assert row is not None and cur.rowcount == 1
    return int(row[0])


def seed_place(
    dbname: str,
    *,
    name: str,
    summary: str = "Fixture place.",
    longitude: float = -73.9857,
    latitude: float = 40.7484,
    place_type: str = "fixed_location",
) -> tuple[int, int]:
    """Insert one located, zoned place; return its place and entity IDs.

    The row takes the production insert shape (``db_converters``): the zone
    is resolved from the point through ``resolve_zone_for_point`` (covering
    zone, else nearest bounded zone), the subtype trigger mints the ``place``
    entity, and the point is a ``PointZM`` geography. The place is on the map,
    and a protagonist placed there has a current zoned place for
    ``story_active_zone``. The save needs a bounded zone first (``seed_zone``);
    without one the resolver raises, as it does in production.
    """

    require_disposable_target(dbname)
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        zone_id = resolve_zone_for_point(cur, longitude=longitude, latitude=latitude)
        cur.execute(
            """
            INSERT INTO places (name, type, summary, zone, coordinates)
            VALUES (
                %s, %s::place_type, %s, %s,
                ST_SetSRID(ST_MakePoint(%s, %s, 0, 0), 4326)::geography
            )
            RETURNING id, entity_id
            """,
            (name, place_type, summary, zone_id, longitude, latitude),
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

    require_disposable_target(dbname)
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

    require_disposable_target(dbname)
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

    require_disposable_target(dbname)
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

    require_disposable_target(dbname)
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


# The TEST provider's registered model id; a fixture turn records it as the
# model that generated the staged prose, as the TEST seats do.
FIXTURE_GENERATION_MODEL = "TEST"


def _run_staging_coroutine(coroutine: Any) -> None:
    """Run the production staging coroutine from a synchronous seed helper."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coroutine)
        return
    coroutine.close()
    raise RuntimeError(
        "seed helpers are synchronous: stage fixture turns from a synchronous "
        "fixture or test, not inside a running event loop"
    )


def _require_slot_routes_to(dbname: str, slot: int | None) -> None:
    """Refuse a slot label that does not route to the disposable target.

    ``slot`` is stamped on the jobs an accepted turn enqueues and handed to
    the production commit, which may resolve story state through it. Tests
    pass a slot only while ``tests.scheduler_helpers.route_slot`` routes that
    slot to the clone; any other routing would reach an owner database.

    ``slot=None`` is checked as the slot the commit resolves: a maturation job
    for a declared entity is labelled with ``get_active_slot()``, the ambient
    ``NEXUS_SLOT``, so a set ``NEXUS_SLOT`` must route to the clone too. With
    ``NEXUS_SLOT`` unset, the commit's own label resolution raises before it
    enqueues a routed job.
    """

    from nexus.api import slot_utils

    if slot is None:
        if os.environ.get("NEXUS_SLOT") is None:
            return
        ambient = slot_utils.get_active_slot()
        routed = slot_utils.slot_dbname(ambient)
        if routed != dbname:
            raise RuntimeError(
                f"Ambient NEXUS_SLOT={ambient} routes to {routed!r}, not the "
                f"disposable target {dbname!r}; pass a slot routed to the clone "
                "or route the ambient slot before seeding turns"
            )
        return
    routed = slot_utils.slot_dbname(slot)
    if routed != dbname:
        raise RuntimeError(
            f"Slot {slot} routes to {routed!r}, not the disposable target "
            f"{dbname!r}; route the slot to the clone before seeding turns"
        )


def _playable_frontier_chunk_id(cur: Any) -> int:
    """Return the committed frontier chunk ID, or 0 before the first turn."""

    from nexus.agents.orrery.reconstruction import playable_narrative_predicate

    cur.execute(
        "SELECT max(nc.id) FROM narrative_chunks nc WHERE "
        + playable_narrative_predicate()
    )
    row = cur.fetchone()
    return int(row[0]) if row is not None and row[0] is not None else 0


def _require_story_preconditions(cur: Any, helper: str) -> None:
    """Fail by name unless the save has a world clock and a canonical player.

    The wizard transition leaves both behind before the first turn: the
    clock anchors every chunk's ``world_time`` and need clock, and the
    canonical player is who the turn is played by. ``seed_protagonist`` (or
    ``seed_played_story``) supplies both.
    """

    from nexus.agents.orrery.player_identity import (
        PlayerIdentityNotEstablishedError,
        canonical_player_character_id,
    )

    cur.execute("SELECT base_timestamp FROM global_variables WHERE id = true")
    row = cur.fetchone()
    assert row is not None and row[0] is not None, (
        f"{helper} needs a world clock: seed_protagonist sets base_timestamp "
        "before the first turn"
    )
    try:
        canonical_player_character_id(cur)
    except PlayerIdentityNotEstablishedError as exc:
        raise AssertionError(
            f"{helper} needs a canonical player: call seed_protagonist first"
        ) from exc


def _require_free_staging_slot(cur: Any, helper: str) -> None:
    """Fail by name unless no draft is pending and no live lease is held.

    ``acquire_generation_lease`` commits a session and a lease before the
    incubator write can refuse a pending draft, so both are checked before
    the lease is taken. An expired lease is not a conflict: acquisition
    replaces it, as in production.
    """

    from nexus.api.narrative_lease import OWNER_EXPIRED_SQL

    cur.execute("SELECT session_id FROM incubator")
    pending = cur.fetchone()
    if pending is not None:
        raise RuntimeError(
            f"{helper} needs an empty incubator: the singleton is owned by "
            f"session {pending[0]}"
        )
    cur.execute(
        "SELECT session_id, operation FROM narrative_generation_lease "
        f"WHERE id = TRUE AND NOT ({OWNER_EXPIRED_SQL})"
    )
    owner = cur.fetchone()
    if owner is not None:
        raise RuntimeError(
            f"{helper} lease conflict: session {owner[0]} holds a live "
            f"{owner[1]!r} lease"
        )


def _default_scene_references(cur: Any) -> dict[str, list[dict[str, Any]]]:
    """Reference the canonical player as present at their current place.

    This is the reference shape Skald stages for an ordinary turn (and the
    bootstrap stages for the opening): the protagonist present, the scene's
    place as its setting. The player must exist; a story without one is a
    missing precondition, not a turn to stage.
    """

    from nexus.agents.orrery.player_identity import canonical_player_character_id

    character_id = canonical_player_character_id(cur)
    cur.execute(
        "SELECT name, current_location FROM characters WHERE id = %s",
        (character_id,),
    )
    name, place_id = cur.fetchone()
    references: dict[str, list[dict[str, Any]]] = {
        "characters": [
            {
                "character_id": character_id,
                "character_name": name,
                "reference_type": "present",
            }
        ],
        "places": [],
        "factions": [],
    }
    if place_id is not None:
        references["places"].append(
            {"place_id": int(place_id), "reference_type": "setting"}
        )
    return references


def _resolve_turn_orrery_proposal(
    dbname: str, *, anchor_chunk_id: int, orrery_settings: Mapping[str, Any]
) -> dict[str, Any]:
    """Resolve the no-write Orrery proposal LORE stages for a continuation.

    Mirrors ``TurnCycleManager.resolve_orrery``: the production resolver runs
    over ``BUILTIN_TEMPLATES`` at the playable frontier with the configured
    Orrery sections, and the proposal is staged by ``_serialize_orrery_staging``
    with an empty Bleed offer manifest (no Bleed menu is offered to a fixture
    turn). The session is read-only and rolled back.
    """

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from nexus.agents.orrery.ambient import shared_ambient_pacing_allows
    from nexus.agents.orrery.resolver import resolve_dry_run
    from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
    from nexus.api.lore_adapter import _serialize_orrery_staging
    from nexus.config.settings_models import OrreryBleedSettings

    bleed = OrreryBleedSettings.model_validate(orrery_settings["bleed"])
    ambient_pacing_allowed = shared_ambient_pacing_allows(
        anchor_chunk_id, bleed.density
    )
    engine = create_engine(sqlalchemy_url(dbname), future=True)
    try:
        with Session(engine) as session:
            proposal = resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=anchor_chunk_id,
                window_chunks=int(orrery_settings["binding"]["window_chunks"]),
                sunhelm_settings=orrery_settings.get("sunhelm"),
                selection_settings=orrery_settings.get("selection"),
                habituation_settings=orrery_settings.get("habituation"),
                package_selection_settings=orrery_settings.get("package_selection"),
                project_settings=orrery_settings.get("projects"),
                epistemics_settings=orrery_settings.get("epistemics"),
                fanout_settings=orrery_settings.get("fanout"),
                contagion_settings=orrery_settings.get("contagion"),
                weather_settings=orrery_settings.get("weather"),
                mood_settings=orrery_settings.get("mood"),
                composition_settings=orrery_settings.get("composition"),
                ambient_settings=orrery_settings.get("ambient"),
                ambient_pacing_allowed=ambient_pacing_allowed,
            )
            session.rollback()
    finally:
        engine.dispose()
    return _serialize_orrery_staging(proposal, bleed_offer_resolution_ids=())


def seed_pending_turn(
    dbname: str,
    *,
    user_text: str,
    storyteller_text: str,
    choices: list[str] | None = None,
    time_delta: timedelta = timedelta(minutes=5),
    episode_transition: str | None = None,
    scene_boundary: bool = False,
    reference_updates: Mapping[str, Any] | None = None,
    entity_updates: Mapping[str, Any] | None = None,
    new_entities: list[Mapping[str, Any]] | None = None,
    correspondence_writer_letter: str | None = None,
    correspondence_gaia_letter: str | None = None,
    generation_model: str = FIXTURE_GENERATION_MODEL,
    resolve_orrery: bool = True,
) -> str:
    """Stage one pending turn exactly as the gateway does; return its session.

    The turn continues the committed frontier (the bootstrap opening, parent
    0, when the story has no playable chunk yet). A continuation stages the
    Orrery proposal LORE would stage, from the production resolver at the
    frontier (``resolve_orrery=False`` stages none, as with Orrery disabled);
    the bootstrap opening stages none, as ``generate_bootstrap_narrative``
    does. Staging takes the production route's steps in the gateway's order:
    lease, bind parent, resolve, write incubator. ``acquire_generation_lease``
    records the ``continue`` session and owns the slot;
    ``bind_generation_parent`` binds the frontier (``continue_narrative``
    takes both steps before it schedules generation); the Orrery proposal is
    resolved under that lease, as the scheduled LORE turn resolves it; and
    ``write_to_incubator`` validates the draft with
    ``validate_commit_draft_sync``, writes the incubator singleton, and
    completes the session while releasing the lease. The draft is the shape
    ``response_to_incubator`` (or ``generate_bootstrap_narrative``) builds:
    ``generation_model`` names the TEST model, ``session_id`` is the staging
    session, the ``lore_pass_baseline`` is the unbound empty baseline that
    bootstrap and ``scripts/stamp_lore_pass_baseline.py`` stage, fingerprinted
    under the current settings and the clone's story pins, and
    ``authorial_directives`` keeps its empty default, so the committed chunk
    satisfies ``playable_narrative_predicate``.

    ``reference_updates`` defaults to the canonical player present at their
    current place. ``time_delta`` must fit the chronology fields (under one
    hour for minutes, under a day for hours). The parent chunk's embedding is
    not claimed: that is the gateway route's step before generation, not part
    of staging or acceptance.

    ``choices`` is empty or at least two presented choices: the gateway
    stages no choice object for fewer than two (``extract_choice_object``), so
    a single choice is refused rather than staged in a shape play never
    writes.

    Fails loudly, before taking the lease, when the save has no world clock
    (``base_timestamp``) or no canonical player, when another session holds a
    live lease, or when a draft is already pending. A failure after the lease
    is taken (binding, resolution, or the incubator write) abandons the
    staging session, releasing its lease, before it propagates.
    """

    require_disposable_target(dbname)
    from nexus.api.config_utils import get_generation_lease_timeout_seconds
    from nexus.api.narrative_generation import write_to_incubator
    from nexus.api.narrative_lease import (
        abandon_generation,
        acquire_generation_lease,
        bind_generation_parent,
    )
    from nexus.config import load_settings
    from nexus.config.story_model import read_story_settings, story_context_settings
    from nexus.memory.manager import empty_pass2_baseline

    if choices and len(choices) < 2:
        raise ValueError(
            "seed_pending_turn needs at least two choices, as Skald presents them"
        )
    total_minutes, remainder = divmod(int(time_delta.total_seconds()), 60)
    if remainder:
        raise ValueError("seed_pending_turn needs a whole-minute time_delta")
    days, minutes_of_day = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(minutes_of_day, 60)
    settings = story_context_settings(load_settings(), read_story_settings(dbname))
    assert settings.orrery is not None, "seed_pending_turn needs an [orrery] section"
    orrery_settings = settings.orrery.model_dump(by_alias=True)
    baseline = empty_pass2_baseline(settings)
    session_id = str(uuid.uuid4())
    with closing(_connect(dbname)) as conn:
        with conn.cursor() as cur:
            _require_story_preconditions(cur, "seed_pending_turn")
            _require_free_staging_slot(cur, "seed_pending_turn")
            parent_chunk_id = _playable_frontier_chunk_id(cur)
            references = (
                dict(reference_updates)
                if reference_updates is not None
                else _default_scene_references(cur)
            )
        conn.rollback()
        is_bootstrap = parent_chunk_id == 0
        conflict = acquire_generation_lease(
            conn,
            session_id=session_id,
            operation="continue",
            stale_timeout_seconds=get_generation_lease_timeout_seconds(),
        )
        assert conflict is None, f"seed_pending_turn lease conflict: {conflict}"
        try:
            bind_generation_parent(
                conn, session_id=session_id, parent_chunk_id=parent_chunk_id
            )
            orrery_proposal = (
                _resolve_turn_orrery_proposal(
                    dbname,
                    anchor_chunk_id=parent_chunk_id,
                    orrery_settings=orrery_settings,
                )
                if resolve_orrery and not is_bootstrap and orrery_settings["enabled"]
                else None
            )
            data: dict[str, Any] = {
                "chunk_id": None,
                "parent_chunk_id": parent_chunk_id,
                "user_text": user_text,
                "storyteller_text": storyteller_text,
                "generation_model": generation_model,
                "choice_object": (
                    {"presented": list(choices), "selected": None} if choices else None
                ),
                "choice_text": None,
                "metadata_updates": {
                    "chronology": {
                        "episode_transition": episode_transition
                        or ("new_episode" if is_bootstrap else "continue"),
                        "time_delta_minutes": minutes,
                        "time_delta_hours": hours or None,
                        "time_delta_days": days or None,
                        "time_delta_description": "Fixture turn",
                    },
                    "world_layer": "primary",
                    "scene_boundary": scene_boundary,
                },
                "entity_updates": dict(entity_updates or {}),
                "reference_updates": references,
                "orrery_proposal": orrery_proposal,
                "orrery_adjudications": [],
                "new_entities": [dict(item) for item in new_entities or []],
                "correspondence_writer_letter": correspondence_writer_letter,
                "correspondence_gaia_letter": correspondence_gaia_letter,
                "lore_pass_baseline": baseline.model_dump(mode="json"),
                "session_id": session_id,
                "llm_response_id": f"fixture_{uuid.uuid4().hex[:8]}",
                "status": "provisional",
            }
            _run_staging_coroutine(
                write_to_incubator(conn, data, complete_session=True)
            )
        except Exception as exc:
            conn.rollback()
            abandon_generation(
                conn,
                session_id=session_id,
                error=f"seed_pending_turn staging failed: {exc!r}",
                error_class=type(exc).__name__,
            )
            raise
        with conn.cursor() as cur:
            cur.execute(
                "SELECT i.parent_chunk_id, s.status, s.terminal_outcome "
                "FROM incubator i JOIN narrative_generation_sessions s "
                "ON s.session_id = i.session_id WHERE i.session_id = %s",
                (session_id,),
            )
            staged = cur.fetchone()
        conn.rollback()
    assert staged == (
        parent_chunk_id,
        "complete",
        None,
    ), f"seed_pending_turn left {staged!r} for session {session_id}"
    return session_id


def seed_accepted_turn(
    dbname: str,
    *,
    user_text: str,
    storyteller_text: str,
    choice_text: str | None = None,
    choices: list[str] | None = None,
    slot: int | None = None,
    **staging: Any,
) -> int:
    """Stage one turn and accept it through the production commit; return its ID.

    The turn is staged by ``seed_pending_turn`` (``staging`` passes through
    to it), the player's response is recorded on the incubator by the
    gateway's own ``_record_player_response_for_chunk``, and the draft is
    committed by ``commit_incubator_to_database_sync`` on the same connection,
    as ``_resolve_and_approve_pending_sync`` does. Every trigger and writer
    of an accepted turn therefore runs: the chunk and its metadata (the world
    clock is stamped by the ``chunk_metadata`` trigger), the bound Pass-2
    baseline, presence and reference rows, the Orrery tick, experience seeds,
    checkpoints, summary scheduling, and the IDF corpus triggers.

    ``choice_text`` is the player's response to this turn's ``choices``: a
    presented choice is selected by its number, other text is recorded as the
    player's own wording. The chunk records the response the gateway resolves
    (``resolve_choice_response`` trims free text), so acceptance is checked
    against that resolved text, never the raw argument. ``slot`` labels the
    jobs the commit enqueues and is accepted only while it routes to
    ``dbname``.
    """

    require_disposable_target(dbname)
    _require_slot_routes_to(dbname, slot)
    from nexus.api.commit_handler_sync import commit_incubator_to_database_sync

    session_id = seed_pending_turn(
        dbname,
        user_text=user_text,
        storyteller_text=storyteller_text,
        choices=choices,
        **staging,
    )
    with closing(_connect(dbname)) as conn:
        resolved_choice_text: str | None = None
        if choice_text is not None:
            from nexus.api.narrative import _record_player_response_for_chunk

            presented = list(choices or [])
            resolved_choice_text = _record_player_response_for_chunk(
                slot=slot,
                chunk_id=None,
                user_text="" if choice_text in presented else choice_text,
                choice=(
                    presented.index(choice_text) + 1
                    if choice_text in presented
                    else None
                ),
                accept_fate=False,
                require_response=True,
                connection=conn,
                incubator_session_id=session_id,
            )
        chunk_id = commit_incubator_to_database_sync(conn, session_id, slot)
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT nc.choice_text, s.terminal_outcome, s.chunk_id,
                       (SELECT count(*) FROM lore_pass_baselines b
                        WHERE b.chunk_id = nc.id),
                       (SELECT count(*) FROM incubator)
                FROM narrative_chunks nc
                JOIN chunk_metadata cm ON cm.chunk_id = nc.id
                JOIN narrative_generation_sessions s ON s.session_id = %s
                WHERE nc.id = %s AND cm.world_time IS NOT NULL
                """,
                (session_id, chunk_id),
            )
            accepted = cur.fetchone()
    assert accepted == (
        resolved_choice_text,
        "accepted",
        chunk_id,
        1,
        0,
    ), f"seed_accepted_turn committed chunk {chunk_id} as {accepted!r}"
    return int(chunk_id)


FIXTURE_TURN_CHOICES = (
    "Press on toward the lit doorway.",
    "Wait and watch the street.",
    "Ask the nearest stranger for directions.",
)


def seed_played_story(
    dbname: str,
    *,
    turns: int,
    protagonist_name: str = "Fixture Player",
    base_timestamp: str = "2100-01-01T00:00:00+00:00",
    time_delta: timedelta = timedelta(minutes=5),
    cast: tuple[str, ...] = (),
    correspondence: bool = False,
    slot: int | None = None,
) -> list[int]:
    """Seed a played story of ``turns`` accepted turns; return their chunk IDs.

    Seeds what the wizard transition leaves behind (a bounded zone, a located
    place, and the canonical player standing there, with the world clock at
    ``base_timestamp``), then accepts the bootstrap opening and ``turns - 1``
    continuations through ``seed_accepted_turn``, each ``time_delta`` of
    story time after the last. Each turn presents ``FIXTURE_TURN_CHOICES``
    and records the first as the player's response; each continuation's input
    is the previous turn's response, as in play.

    ``cast`` names off-screen characters, seeded at a second place and
    mentioned by every turn's prose and references. Mentioned characters are
    the Orrery's actors, so continuations stage real resolver proposals for
    them and acceptance writes their resolutions, events, and experience
    seeds. ``correspondence`` stages a writer and a Gaia letter with every
    turn, as the two-pass seats do.

    Refuses a save that already holds a player or narrative.
    """

    require_disposable_target(dbname)
    _require_slot_routes_to(dbname, slot)
    if turns < 1:
        raise ValueError("seed_played_story needs at least one turn")
    with closing(_connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT (SELECT user_character FROM global_variables WHERE id = true), "
            "(SELECT count(*) FROM narrative_chunks)"
        )
        player, chunk_count = cur.fetchone()
    assert player is None and chunk_count == 0, (
        f"seed_played_story needs an unplayed save; {dbname} has player "
        f"{player!r} and {chunk_count} chunks"
    )
    seed_zone(
        dbname,
        name="Fixture Zone",
        min_longitude=-74.1,
        min_latitude=40.6,
        max_longitude=-73.8,
        max_latitude=40.9,
    )
    place_id, _ = seed_place(dbname, name="Fixture Plaza")
    player_id, _ = seed_protagonist(
        dbname,
        name=protagonist_name,
        base_timestamp=base_timestamp,
        current_location=place_id,
    )
    references: dict[str, list[dict[str, Any]]] = {
        "characters": [
            {
                "character_id": player_id,
                "character_name": protagonist_name,
                "reference_type": "present",
            }
        ],
        "places": [{"place_id": place_id, "reference_type": "setting"}],
        "factions": [],
    }
    offstage = ""
    if cast:
        elsewhere_id, _ = seed_place(
            dbname, name="Fixture Docks", longitude=-74.0, latitude=40.7
        )
        for name in cast:
            character_id, _ = seed_character(
                dbname,
                name=name,
                summary=f"{name} works the night shift at Fixture Docks.",
                current_location=elsewhere_id,
            )
            references["characters"].append(
                {
                    "character_id": character_id,
                    "character_name": name,
                    "reference_type": "mentioned",
                }
            )
        offstage = (
            f" Across town at Fixture Docks, {' and '.join(cast)} "
            "keep to their own business."
        )
    chunk_ids: list[int] = []
    user_text = "Begin the story."
    for turn in range(1, turns + 1):
        chunk_ids.append(
            seed_accepted_turn(
                dbname,
                user_text=user_text,
                storyteller_text=(
                    f"Fixture turn {turn}: {protagonist_name} crosses Fixture "
                    f"Plaza as the evening crowd thins.{offstage}"
                ),
                choices=list(FIXTURE_TURN_CHOICES),
                choice_text=FIXTURE_TURN_CHOICES[0],
                time_delta=timedelta(0) if turn == 1 else time_delta,
                reference_updates=references,
                correspondence_writer_letter=(
                    f"Writer note for fixture turn {turn}." if correspondence else None
                ),
                correspondence_gaia_letter=(
                    f"Gaia note for fixture turn {turn}." if correspondence else None
                ),
                slot=slot,
            )
        )
        user_text = FIXTURE_TURN_CHOICES[0]
    return chunk_ids
