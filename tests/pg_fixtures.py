"""Shared PostgreSQL helpers for disposable integration-test databases."""

from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn
from sqlalchemy import text
from sqlalchemy.engine import URL

from nexus.api import db_pool
from nexus.config.story_model import StorySettings, write_story_settings
from nexus.database import connection_kwargs, create_slot_engine, database_url
from scripts import migrate, new_story_setup


def connection_parameters() -> dict[str, str]:
    """Return the PG* environment as keyword parameters, never a hand-built URI.

    Keyword parameters survive Unix-socket directories (`PGHOST=/var/run/...`)
    and IPv6 hosts (`::1`) that break naive URI interpolation.
    """

    return {
        "user": os.environ.get("PGUSER", "pythagor"),
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
    }


def connect(dbname: str, *, cursor_factory: Any = None) -> Any:
    """Open a direct psycopg2 connection to ``dbname``."""

    kwargs: dict[str, Any] = {"dbname": dbname, **connection_parameters()}
    if cursor_factory is not None:
        kwargs["cursor_factory"] = cursor_factory
    return psycopg2.connect(**kwargs)


def asyncpg_kwargs(dbname: str) -> dict[str, Any]:
    """Return keyword arguments for ``asyncpg.connect`` targeting ``dbname``."""

    params = connection_parameters()
    return {
        "database": dbname,
        "user": params["user"],
        "host": params["host"],
        "port": int(params["port"]),
    }


def sqlalchemy_url(dbname: str) -> URL:
    """Return a SQLAlchemy URL for ``dbname`` built through ``URL.create``."""

    params = connection_parameters()
    return URL.create(
        "postgresql",
        username=params["user"],
        host=params["host"],
        port=int(params["port"]),
        database=dbname,
    )


_connect = connect

_TARGET_IDENTITY_SQL = (
    "SELECT current_database(), current_setting('port'), "
    "(pg_postmaster_start_time() AT TIME ZONE 'UTC')::text"
)


def assert_one_target(dbname: str) -> None:
    """Fail unless fixture, runtime, and URL clients reach one database.

    Fixtures seed through ``connect`` (the PG* environment), while production
    code resolves ``nexus.database`` directly or through ``database_url``. If
    the two disagree, a test seeds one server and queries another (issue
    #804). The server's listening port and postmaster start time identify the
    instance whether a client arrives over TCP or a Unix socket.

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
    # The clone is created and migrated through nexus.database but dropped
    # through the PG* admin connection below. Prove both reach one server
    # before creating anything, so a clone cannot outlive its fixture.
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
                subprocess.run(
                    [
                        "pg_dump",
                        "--format=custom",
                        "--file",
                        archive_path,
                        "--dbname",
                        make_dsn(dbname=source_db, **connection_parameters()),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    [
                        "pg_restore",
                        "--exit-on-error",
                        "--no-owner",
                        "--no-acl",
                        "--dbname",
                        make_dsn(dbname=dbname, **connection_parameters()),
                        archive_path,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
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


def seed_protagonist(
    dbname: str,
    *,
    name: str = "Fixture Player",
    summary: str = "Canonical player for PostgreSQL coverage.",
    base_timestamp: str = "2100-01-01T00:00:00+00:00",
) -> tuple[int, int]:
    """Bind a fixture-owned player to the save and return character/entity IDs."""

    with _connect(dbname) as conn:
        with conn.cursor() as cur:
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
                INSERT INTO characters (name, summary, entity_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (name, summary, entity_id),
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
) -> int:
    """Insert one committed chunk with its primary-layer metadata; return its ID."""

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
                %s, %s, %s, %s, 'primary', interval '1 minute', now(), %s
            )
            """,
            (
                chunk_id,
                season,
                episode,
                scene,
                f"S{season:02d}E{episode:02d}_{scene:03d}",
            ),
        )
    return chunk_id
