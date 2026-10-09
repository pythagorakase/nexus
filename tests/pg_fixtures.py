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
save slots, ``NEXUS_template``, and the legacy TEST database ``mock`` by name.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import psycopg2
from psycopg2 import sql
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url

from nexus.agents.orrery.geo import resolve_zone_for_point
from nexus.api import db_pool
from nexus.api.slot_utils import all_slots, slot_dbname
from nexus.api.story_identity import detach_clone_identity
from nexus.config import load_settings
from nexus.config.loader import TEST_PROVIDER_DATABASE_ENV
from nexus.config.settings_models import Settings
from nexus.config.story_model import (
    StorySettings,
    resolve_seat,
    write_story_settings,
)
from nexus.database import (
    asyncpg_kwargs as contract_asyncpg_kwargs,
    connection_kwargs,
    create_slot_engine,
    database_url,
    subprocess_env,
)
from nexus.maintenance import migrate
from nexus.maintenance import new_story_setup


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


# Migration 126 freezes queued and leased jobs' models from the story pin it
# finds. Its JOB_SEATS maps each job table it backfills to the seat that
# resolves that table's model.
SEAT_BACKFILL_MIGRATION = "126"


def seat_backfill_job_seats() -> dict[str, str]:
    """Return migration 126's ``JOB_SEATS`` (job table to model seat).

    The mapping is read from the migration module itself, loaded through
    ``nexus.maintenance.migrate``'s importlib loader, so the guard below cannot drift
    from the tables the migration backfills.
    """

    paths = [
        path
        for version, _, path in migrate.discover_migrations()
        if version == SEAT_BACKFILL_MIGRATION
    ]
    if len(paths) != 1:
        raise RuntimeError(
            f"Expected one migration {SEAT_BACKFILL_MIGRATION}, found {paths!r}"
        )
    module = migrate._load_python_migration(paths[0])
    return dict(module.JOB_SEATS)


def _has_migration_stamp(dbname: str, version: str) -> bool:
    """Return whether ``dbname``'s ``schema_migrations`` records ``version``."""

    with closing(_connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
        if not cur.fetchone()[0]:
            return False
        cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
        return cur.fetchone() is not None


def _refuse_source_pin_backfill(dbname: str, story_pin: str) -> None:
    """Raise when migration 126 froze a job to a model the clone's pin would not pick.

    A data clone migrates before it is pinned, so migration 126 resolves its
    queued and leased jobs under the source's story pin, and that resolution
    is immutable across repins. Only a seat whose policy follows the story can
    resolve differently under the clone's pin; a fixed seat resolves to its
    configured default under any pin. The guard therefore refuses only
    backfilled rows whose frozen model differs from what ``story_pin`` resolves
    for the table's seat: a worker would route those jobs to the source's
    model.
    """

    settings = load_settings()
    story = StorySettings(skald_model=story_pin, gaia_model=None)
    with closing(_connect(dbname)) as conn, conn.cursor() as cur:
        for table, seat in seat_backfill_job_seats().items():
            expected = resolve_seat(seat, settings=settings, story=story).model
            cur.execute(
                sql.SQL(
                    "SELECT count(*), array_agg(DISTINCT resolved_model) FROM {} "
                    "WHERE state IN ('queued', 'leased') "
                    "AND resolved_source = 'migration_backfill' "
                    "AND resolved_model IS DISTINCT FROM %s"
                ).format(sql.Identifier(table)),
                (expected,),
            )
            frozen, models = cur.fetchone()
            if frozen:
                raise RuntimeError(
                    f"Data clone {dbname}: migration 126 froze {frozen} active "
                    f"{table} rows to {models!r} under the source's story pin; "
                    f"the {story_pin!r} pin resolves seat {seat} to {expected!r} "
                    "and cannot replace the frozen model"
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
    only, suitable for tests that create their own stories. A data clone is
    brought to the current migration stamp before the TEST pin is written,
    because the pin names columns that a source behind the current stamp may
    lack (``global_variables.gaia_model`` arrives in migration 117; issue
    #1083). Migrations call no provider, and the fixture yields only after the
    pin, so ``global_variables`` reads the TEST pin. Migration 126 is the one
    exception the pin cannot reach: it freezes ``resolved_model`` on queued and
    leased jobs from the pin it finds, which for a data clone is the source's
    pin, and a later repin does not change it. That matters only for seats
    whose policy follows the story; a fixed seat resolves to its configured
    default under any pin. When the clone crosses 126 under a TEST pin, the
    fixture fails loudly instead of yielding if any backfilled job
    (``resolved_source = 'migration_backfill'``) carries a model other than
    the one the TEST pin resolves for its seat. Jobs the source already
    resolved before the clone keep their models. Preserving the source pin
    requires the explicit live-LLM opt-in.

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
            crosses_seat_backfill = not _has_migration_stamp(
                dbname, SEAT_BACKFILL_MIGRATION
            )
            # Migrate before pinning: the pin's UPDATE names columns (such as
            # global_variables.gaia_model) that a source behind the current
            # stamp does not have yet.
            _, failed = migrate.migrate_database(dbname, skip_locked=False)
            if failed:
                raise RuntimeError(
                    f"Corpus clone {dbname} has {failed} failed migrations"
                )
            detach_clone_identity(dbname)
            if story_pin is not None and crosses_seat_backfill:
                _refuse_source_pin_backfill(dbname, story_pin)
            pin_clone()
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
    {"NEXUS_template", "mock", *(slot_dbname(slot) for slot in all_slots())}
)


def require_disposable_target(dbname: str) -> str:
    """Return ``dbname`` unless it names an owner database, which raises.

    The owner databases are ``NEXUS_template``, the owner's TEST provider
    database ``mock``, and every save slot that ``nexus.api.slot_utils``
    defines (``save_01`` through ``save_05``). A seed
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


_SEED_TEST_PROVIDER_SCRIPT = (
    Path(__file__).resolve().parents[1] / "migrations" / "008_populate_mock_database.py"
)


@contextmanager
def disposable_test_provider_database(
    prefix: str = "qa640_816_test_provider",
) -> Iterator[str]:
    """Yield a template clone seeded as a TEST provider database, then drop it.

    The clone comes from ``disposable_slot_database`` (TEST-pinned) and is
    seeded by migration 008's ``seed_test_provider_database``, the production
    seeding path, in one transaction. Route it to this process and its children
    with ``route_test_provider_database``.
    """

    spec = importlib.util.spec_from_file_location(
        "migrations_008_populate_mock_database", _SEED_TEST_PROVIDER_SCRIPT
    )
    assert spec is not None and spec.loader is not None, _SEED_TEST_PROVIDER_SCRIPT
    seeder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seeder)
    with disposable_slot_database(prefix) as dbname:
        seeder.seed_test_provider_database(dbname)
        yield dbname


def route_test_provider_database(
    setenv: Callable[[str, str], None], dbname: str
) -> None:
    """Name ``dbname`` as the TEST provider database through the environment.

    ``setenv`` is the caller's setter (``monkeypatch.setenv``), so the route is
    undone with the caller's scope. ``load_settings`` overlays the variable
    before validation, and child processes inherit it at spawn. Owner databases
    are refused.
    """

    require_disposable_target(dbname)
    setenv(TEST_PROVIDER_DATABASE_ENV, dbname)


# The unrouted slot resolver, captured at import under a name the routing
# sweep below never rebinds.
_UNROUTED_SLOT_DBNAME = slot_dbname

# The repository's ``tests/`` directory. Pytest imports a test module under a
# name relative to its first directory without an ``__init__.py`` (a module in
# ``tests/test_runtime/`` loads as ``test_runtime.<name>``), so the routing
# sweep recognizes repository test modules by file as well as by name.
_TESTS_DIR = Path(__file__).resolve().parent

# The package prefixes the routing sweep rebinds by module name.
_SWEPT_PACKAGES = ("nexus.", "scripts.", "tests.")


def _is_swept_module(name: str, module: types.ModuleType) -> bool:
    """Whether the routing sweep rebinds ``module``'s bound slot resolver.

    Modules of this repository's ``nexus``, ``scripts``, and ``tests``
    packages are swept by name; any other module is swept when its resolved
    ``__file__`` lies under this repository's ``tests/`` directory, whatever
    name pytest imported it under.
    """

    if name.startswith(_SWEPT_PACKAGES):
        return True
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        return False
    return Path(module_file).resolve().is_relative_to(_TESTS_DIR)


# The active routes as a read-only ``{slot: dbname}`` mapping, or ``None``
# when no slot is routed. ``route_slots_to_disposable`` sets it through its
# ``patch`` callable, so a test's monkeypatch restores the previous routes
# (usually ``None``) at teardown.
_ACTIVE_ROUTE: Mapping[int, str] | None = None


def _describe_routes(routes: Mapping[int, str]) -> str:
    """Name the routed slots and their clones for a refusal message."""

    return ", ".join(
        f"slot {slot} -> {dbname!r}" for slot, dbname in sorted(routes.items())
    )


def _routed_slot_dbname(slot_number: int) -> str:
    """Resolve a slot through the active routes, or unrouted when none is set.

    This one function is what every routed module binds, including a module
    whose ``from nexus.api.slot_utils import slot_dbname`` first runs while a
    route is active, which ``patch`` never records and so never undoes. Such
    a binding stays correct after teardown: with ``_ACTIVE_ROUTE`` restored to
    ``None`` it resolves exactly as ``_UNROUTED_SLOT_DBNAME`` does, and a later
    route reaches it without another sweep. A slot the active routes do not
    map raises ``RuntimeError``.
    """

    routes = _ACTIVE_ROUTE
    if routes is None:
        return _UNROUTED_SLOT_DBNAME(slot_number)
    dbname = routes.get(slot_number)
    if dbname is None:
        raise RuntimeError(
            f"Slot {slot_number} is not routed: only {_describe_routes(routes)} "
            "reach disposable clones"
        )
    return dbname


def active_slot_routes() -> Mapping[int, str] | None:
    """Return the active ``{slot: dbname}`` routes, or ``None`` when unrouted.

    The mapping is read-only. A helper that starts a child process reads it
    to hand the child the same route (``routed_slot_environment``).
    """

    return _ACTIVE_ROUTE


def route_slots_to_disposable(
    patch: Callable[[Any, str, Any], None], routes: Mapping[int, str]
) -> None:
    """Route each slot in ``routes`` to its disposable clone in every loaded module.

    Production code resolves a slot's database through
    ``nexus.api.slot_utils.slot_dbname``, either through the module attribute
    (``require_slot_dbname``, ``get_slot_db_url``, ``connection_kwargs`` and
    every function-local import) or through a name bound at import
    (``from nexus.api.slot_utils import slot_dbname``, aliased or not).
    ``patch`` sets the active routes, then rebinds the module attribute and
    every module attribute whose value is the unrouted resolver, whatever its
    name, in every loaded ``nexus``, ``scripts``, or ``tests`` module, and in every
    module whose file lies under this repository's ``tests/`` directory
    (pytest imports ``tests/test_runtime/test_x.py`` as
    ``test_runtime.test_x``), to ``_routed_slot_dbname``, which returns the mapped
    clone for a routed slot and raises ``RuntimeError`` for any other slot,
    and narrows ``VALID_DBNAMES`` to the clones, so a path this sweep missed
    fails loudly instead of reaching an owner database. Modules imported
    afterward bind the same resolver, which falls back to the unrouted
    contract once ``patch`` has restored the routes at teardown.

    Every slot must be one ``nexus.api.slot_utils`` defines and every clone
    must pass ``require_disposable_target``; both are checked before anything
    is patched. A second call replaces the routes; its ``patch`` restores the
    earlier ones at teardown.

    ``patch`` is ``monkeypatch.setattr`` inside a test (undone at teardown) or
    the builtin ``setattr`` in a child process that serves the gateway for
    the clone (``tests.slot_routed_gateway``). The caller sets ``NEXUS_SLOT``
    when the code under test resolves the active slot.
    """

    from nexus.api import slot_utils

    if not routes:
        raise RuntimeError("route_slots_to_disposable needs at least one slot")
    for slot, dbname in routes.items():
        if slot not in all_slots():
            raise RuntimeError(
                f"Cannot route slot {slot!r}: slots are {list(all_slots())}"
            )
        require_disposable_target(dbname)
    frozen = types.MappingProxyType(dict(routes))

    patch(sys.modules[__name__], "_ACTIVE_ROUTE", frozen)
    patch(slot_utils, "VALID_DBNAMES", set(frozen.values()))
    patch(slot_utils, "slot_dbname", _routed_slot_dbname)
    this_module = sys.modules[__name__]
    for name, module in list(sys.modules.items()):
        if module is None:
            continue
        # Sweep by identity, whatever the binding is called: an aliased import
        # (``from nexus.api.slot_utils import slot_dbname as sd``) holds the
        # same unrouted function. The identity scan comes first: it is cheap,
        # and only a module that bound the unrouted resolver needs its file
        # resolved.
        bound = [
            attribute
            for attribute, value in list(vars(module).items())
            if value is _UNROUTED_SLOT_DBNAME
            and not (module is this_module and attribute == "_UNROUTED_SLOT_DBNAME")
        ]
        if bound and _is_swept_module(name, module):
            for attribute in bound:
                patch(module, attribute, _routed_slot_dbname)


def route_slot_to_disposable(
    patch: Callable[[Any, str, Any], None], *, slot: int, dbname: str
) -> None:
    """Route one slot number to a disposable clone in every loaded module.

    The one-slot case of ``route_slots_to_disposable``: ``slot`` resolves to
    ``dbname`` and every other slot raises ``RuntimeError``.
    """

    route_slots_to_disposable(patch, {slot: dbname})


def admit_disposable_database(
    patch: Callable[[Any, str, Any], None], dbname: str
) -> None:
    """Admit ``dbname`` to ``require_slot_dbname`` without routing any slot.

    Only for a test whose slot databases live on a private cluster it starts
    itself (``test_connection_lifecycle``), where the slot names must keep
    resolving to that cluster's own ``save_NN`` databases. ``dbname`` must pass
    ``require_disposable_target``. Every test on the shared cluster routes a
    slot with ``route_slot_to_disposable`` instead, which also refuses owner
    names and unrouted slots.
    """

    from nexus.api import slot_utils

    require_disposable_target(dbname)
    patch(slot_utils, "VALID_DBNAMES", slot_utils.VALID_DBNAMES | {dbname})


# The two variables that route a child process's slot to a clone. The routed
# entry points (``tests.slot_routed_gateway``, ``tests.slot_routed_uvicorn``
# and ``tests.slot_routed_cli``) read them through
# ``route_slot_from_environment`` before any gateway or CLI module loads.
ROUTED_SLOT_ENV = "NEXUS_ROUTED_SLOT"
ROUTED_SLOT_DATABASE_ENV = "NEXUS_ROUTED_SLOT_DATABASE"


def _require_routable_database(dbname: str) -> str:
    """Return ``dbname`` unless it names an owner database, which raises.

    The routing counterpart of ``require_disposable_target``: the refusal
    names ``NEXUS_ROUTED_SLOT_DATABASE``, the variable that carries the
    database into a routed child process, rather than a seed helper.
    """

    if dbname in _OWNER_DATABASES:
        raise RuntimeError(
            f"{ROUTED_SLOT_DATABASE_ENV}={dbname!r} names an owner database; "
            "a routed entry point serves only a disposable clone"
        )
    return dbname


def routed_slot_environment(slot: int, dbname: str) -> dict[str, str]:
    """Return the child-process variables that route ``slot`` to ``dbname``.

    Refuses an owner database here as well, so a caller never builds an
    environment that the child would refuse only after it started.
    """

    _require_routable_database(dbname)
    return {ROUTED_SLOT_ENV: str(slot), ROUTED_SLOT_DATABASE_ENV: dbname}


def route_slot_from_environment(
    environ: Mapping[str, str] | None = None,
) -> tuple[int, str]:
    """Route this process's slot from ``NEXUS_ROUTED_SLOT*`` and return it.

    A routed child-process entry point calls this first. Both variables are
    required, the slot must be one ``nexus.api.slot_utils`` defines, and the
    database must not be an owner database; each failure raises
    ``RuntimeError`` before anything is patched or any connection opens, so
    an unrouted child never falls back to the slot's owner database. The
    route is applied with the builtin ``setattr`` and lasts for the life of
    the process.
    """

    env = os.environ if environ is None else environ
    missing = [
        name
        for name in (ROUTED_SLOT_ENV, ROUTED_SLOT_DATABASE_ENV)
        if not env.get(name)
    ]
    if missing:
        raise RuntimeError(
            "A routed entry point needs "
            + " and ".join(missing)
            + ": it serves only a disposable clone and never an owner slot"
        )
    raw_slot = env[ROUTED_SLOT_ENV]
    try:
        slot = int(raw_slot)
    except ValueError:
        raise RuntimeError(
            f"{ROUTED_SLOT_ENV} must be a slot number, got {raw_slot!r}"
        ) from None
    if slot not in all_slots():
        raise RuntimeError(
            f"{ROUTED_SLOT_ENV}={slot} is not a slot; slots are {all_slots()}"
        )
    dbname = _require_routable_database(env[ROUTED_SLOT_DATABASE_ENV])
    route_slot_to_disposable(setattr, slot=slot, dbname=dbname)
    return slot, dbname


DEFAULT_BASE_TIMESTAMP = "2100-01-01T00:00:00+00:00"


def set_story_base(cur: Any, base_timestamp: str | datetime) -> None:
    """Set ``global_variables.base_timestamp`` on ``cur``'s open transaction.

    This is the one base path for fixtures. Call it before any
    ``chunk_metadata`` row exists, as the wizard transition does: the refresh
    trigger raises on a chunk write while the base is NULL or its row is
    missing (migration 144 removed the wall-clock fallback), and
    ``trg_global_variables_base_timestamp_fixed`` refuses to change the base
    once ``chunk_metadata`` holds a row, because stored event times would keep
    the old clock. The helper upserts the singleton row and checks nothing
    else; the guard is the database's.
    """

    cur.execute(
        "INSERT INTO global_variables (id, base_timestamp) VALUES (true, %s) "
        "ON CONFLICT (id) DO UPDATE SET base_timestamp = EXCLUDED.base_timestamp",
        (base_timestamp,),
    )
    assert cur.rowcount == 1


def seed_story_base(
    dbname: str, *, base_timestamp: str | datetime = DEFAULT_BASE_TIMESTAMP
) -> None:
    """Seed the story clock's base on a disposable save before any chunk.

    A chunk written before the base raises (migration 144: no wall-clock
    fallback), and the base cannot change once a chunk exists, so tests that
    insert chunks without a protagonist call this first. Writes through
    ``set_story_base`` on one connection.
    """

    require_disposable_target(dbname)
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        set_story_base(cur, base_timestamp)


def seed_protagonist(
    dbname: str,
    *,
    name: str = "Fixture Player",
    summary: str = "Canonical player for PostgreSQL coverage.",
    base_timestamp: str = DEFAULT_BASE_TIMESTAMP,
    current_location: int | None = None,
) -> tuple[int, int]:
    """Bind a fixture-owned player to the save and return character/entity IDs.

    Sets ``global_variables.base_timestamp`` before the character insert, which
    satisfies the need-clock anchor (migration 100); ``seed_story_clock`` can
    then add a head chunk after it. Refuses to move a clock that is already
    set (for example by ``seed_story_clock``): once ``chunk_metadata`` holds a
    row, ``trg_global_variables_base_timestamp_fixed`` (migration 144) refuses
    any change to ``base_timestamp``, and before the first chunk a second,
    different base would contradict the clock a caller already seeded.
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
            set_story_base(cur, base_timestamp)
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
    time_delta: timedelta | None = None,
) -> int:
    """Insert one committed chunk with its primary-layer metadata; return its ID.

    ``time_delta`` is the story time elapsing during the chunk. ``None`` means
    zero when the save has no ``chunk_metadata`` row, because the bootstrap
    chunk elapses no time (``base_timestamp`` is the clock at its end, and the
    refresh trigger raises on a non-zero bootstrap delta), and one minute
    otherwise; an explicit value passes through unchanged. The
    statement-level ``trg_chunk_metadata_refresh_world_time`` trigger stamps
    ``chunk_metadata.world_time`` as ``base_timestamp`` plus the cumulative
    primary-layer deltas; the insert raises while ``base_timestamp`` is NULL,
    so seed it first (``seed_story_base``, ``seed_protagonist``, or
    ``seed_story_clock``).

    The chunk carries no ``authorial_directives``, so it satisfies
    ``playable_narrative_predicate`` (reconstruction.py) and counts toward the
    playable ordinal and head-chunk reads.
    """

    require_disposable_target(dbname)
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        if time_delta is None:
            cur.execute("SELECT EXISTS (SELECT 1 FROM chunk_metadata)")
            has_chunks = bool(cur.fetchone()[0])
            time_delta = timedelta(minutes=1) if has_chunks else timedelta(0)
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
    ``world_time`` equals ``base_timestamp`` plus the summed primary-layer
    deltas.
    """

    cur.execute(
        """
        SELECT
            gv.base_timestamp,
            (SELECT count(*) FROM chunk_metadata),
            (SELECT max(world_time) FROM chunk_metadata),
            gv.base_timestamp + COALESCE(
                (SELECT sum(COALESCE(time_delta, interval '0'))
                     FILTER (WHERE world_layer = 'primary')
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
        f"summed primary-layer deltas ({expected_head}); seed "
        "base_timestamp through set_story_base before any chunk"
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
    bootstrap clock and the chunk elapses no time. When ``base_timestamp`` is
    set and the save has no chunk, ``world_time`` must equal
    ``base_timestamp`` (the bootstrap contract: ``base_timestamp`` is the
    clock at the end of the bootstrap chunk, which elapses no time).
    Otherwise the chunk's ``time_delta`` is the gap from the current head
    clock, which must not be later than ``world_time``. The chunk is inserted
    through ``seed_committed_chunk``; the stored ``world_time`` is asserted
    exact and the chunk ID returned.
    """

    require_disposable_target(dbname)
    if world_time.tzinfo is None:
        raise ValueError("seed_story_clock needs a timezone-aware world_time")
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT base_timestamp FROM global_variables WHERE id = true")
        row = cur.fetchone()
        assert row is not None, f"{dbname} has no global_variables row"
        if row[0] is None:
            set_story_base(cur, world_time)
        else:
            cur.execute("SELECT EXISTS (SELECT 1 FROM chunk_metadata)")
            if not cur.fetchone()[0]:
                assert world_time == row[0], (
                    f"seed_story_clock would seed the bootstrap chunk at "
                    f"{world_time}, but base_timestamp is {row[0]}: the bootstrap "
                    "contract makes base_timestamp the clock at the end of the "
                    "bootstrap chunk, which elapses no time; pass the same "
                    "instant to seed_protagonist(base_timestamp=...)"
                )
        cur.execute(
            """
            SELECT gv.base_timestamp + COALESCE(
                (SELECT sum(COALESCE(time_delta, interval '0'))
                     FILTER (WHERE world_layer = 'primary')
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


def seed_story_setting(dbname: str, *, setting: Mapping[str, Any]) -> None:
    """Persist a wizard setting card as the save's ``global_variables.setting``.

    ``setting`` is validated as a ``SettingCard`` and written through
    ``NewStoryDatabaseMapper.save_setting_to_globals``, the statement the
    wizard's new-story transition runs, so the stored payload has the shape
    that runtime readers such as Retrograde maturation's genre weird band
    expect. The stored value is asserted equal to the card's JSON form.
    """

    from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
    from nexus.api.new_story_schemas import SettingCard

    require_disposable_target(dbname)
    card = SettingCard.model_validate(setting)
    expected = json.loads(json.dumps(card.model_dump()))
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        NewStoryDatabaseMapper(dbname).save_setting_to_globals(card, cursor=cur)
        assert cur.rowcount == 1, f"{dbname} has no global_variables row"
        cur.execute("SELECT setting FROM global_variables WHERE id = true")
        stored = cur.fetchone()[0]
    assert (
        stored == expected
    ), f"seed_story_setting stored {stored!r}, expected {expected!r}"


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


class CharacterPairSeed(NamedTuple):
    """The IDs ``seed_character_pair`` seeded, and the clock it anchored."""

    actor_entity_id: int
    target_entity_id: int
    actor_character_id: int
    target_character_id: int
    chunk_id: int
    world_time: datetime


def seed_character_pair(
    dbname: str,
    *,
    world_time: datetime,
    actor_name: str,
    target_name: str,
) -> CharacterPairSeed:
    """Seed a clocked chunk and two active characters; return their IDs.

    Replaces the "first two characters by id plus the latest clocked chunk"
    reads that applier tests once made against an owner save. The story clock
    comes first (``seed_story_clock``), because it is the need-clock anchor
    that ``seed_character`` requires; the actor and the target follow. The
    returned ``chunk_id`` is the clocked chunk, stamped exactly at
    ``world_time``, for use as a source chunk.

    A later call on the same save adds another chunk (the next scene of
    season 1, episode 1) at ``world_time``, which must not be earlier than
    the current head clock (``seed_story_clock``
    refuses to move the clock backward), and two new characters. The seeded
    rows are read back and their counts asserted.
    """

    require_disposable_target(dbname)
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        # A later pair's chunk takes the next scene so its slug stays unique.
        cur.execute(
            "SELECT COALESCE(max(scene), 0) + 1 FROM chunk_metadata "
            "WHERE season = 1 AND episode = 1"
        )
        scene = int(cur.fetchone()[0])
    chunk_id = seed_story_clock(dbname, world_time=world_time, scene=scene)
    actor_character_id, actor_entity_id = seed_character(dbname, name=actor_name)
    target_character_id, target_entity_id = seed_character(dbname, name=target_name)
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM characters c
            JOIN entities e ON e.id = c.entity_id
            WHERE e.kind = 'character' AND e.is_active
              AND (c.id, c.entity_id, c.name) IN ((%s, %s, %s), (%s, %s, %s))
            """,
            (
                actor_character_id,
                actor_entity_id,
                actor_name,
                target_character_id,
                target_entity_id,
                target_name,
            ),
        )
        assert cur.fetchone()[0] == 2, (
            f"seed_character_pair found fewer than two active characters for "
            f"{actor_name!r} and {target_name!r}"
        )
        cur.execute(
            "SELECT count(*) FROM chunk_metadata "
            "WHERE chunk_id = %s AND world_time = %s",
            (chunk_id, world_time),
        )
        assert (
            cur.fetchone()[0] == 1
        ), f"seed_character_pair found no chunk {chunk_id} clocked at {world_time}"
    return CharacterPairSeed(
        actor_entity_id=actor_entity_id,
        target_entity_id=target_entity_id,
        actor_character_id=actor_character_id,
        target_character_id=target_character_id,
        chunk_id=chunk_id,
        world_time=world_time,
    )


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


def seed_faction_membership(
    dbname: str,
    *,
    character_id: int,
    faction_id: int,
    role: str,
) -> tuple[int, int]:
    """Insert one faction-character row with ``role``; return its key.

    ``faction_character_relationships`` is keyed by ``(faction_id,
    character_id)``, so a character holds one role per faction. The
    relationship-versioning trigger refuses any write without a
    transaction-local ``nexus.write_producer``, so the insert is attributed to
    ``manual``. ``role`` must be a ``faction_member_role`` label; the cast
    fails loudly on any other value.
    """

    require_disposable_target(dbname)
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SET LOCAL nexus.write_producer = 'manual'")
        cur.execute(
            """
            INSERT INTO faction_character_relationships (
                faction_id, character_id, role
            ) VALUES (%s, %s, %s::faction_member_role)
            RETURNING faction_id, character_id
            """,
            (faction_id, character_id, role),
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


def _resolve_bestowable_tag(
    cur: Any, *, entity_id: int, tag: str
) -> tuple[int, str, str, bool | None]:
    """Resolve ``tag`` for ``entity_id``'s kind; return its registry standing.

    Returns ``(tag_id, category, entity_kind, category_deprecated)``, where
    ``category_deprecated`` is ``None`` when ``tag_category_registry`` has no
    ``(category, entity_kind)`` row. An unknown or deprecated tag, or a missing
    entity, fails the assertion.
    """

    cur.execute(
        """
        SELECT t.id, t.category, e.kind::text, r.deprecated
        FROM tags t
        CROSS JOIN entities e
        LEFT JOIN tag_category_registry r
          ON r.category = t.category AND r.entity_kind = e.kind
        WHERE t.tag = %s AND NOT t.deprecated AND e.id = %s
        """,
        (tag, entity_id),
    )
    rows = cur.fetchall()
    assert (
        len(rows) == 1
    ), f"tag {tag!r} is not seeded (or entity {entity_id} is missing)"
    tag_id, category, entity_kind, category_deprecated = rows[0]
    return int(tag_id), str(category), str(entity_kind), category_deprecated


def seed_entity_tag(
    dbname: str,
    *,
    entity_id: int,
    tag: str,
    source_kind: str = "template",
) -> int:
    """Bestow one active, registered, live-category tag on an entity.

    Returns the ``entity_tags`` row ID. ``tag`` must be a non-deprecated tag
    from the template's seeded vocabulary whose category is registered live in
    ``tag_category_registry`` for the entity's kind; an unknown or deprecated
    tag fails the assertion. A tag in a deprecated category (migration 043
    deprecated categories and left their tags live, so ``gray_legal`` under
    ``legitimacy_status`` still resolves) raises ``ValueError`` naming the
    category: a faction's goes through ``seed_legacy_faction_tag`` and any
    other kind's through ``seed_deprecated_category_tag``. A category with no
    registry row for the entity's kind raises too. The row is active
    (``cleared_at`` NULL), so checkpoints and ``entity_tags_current`` see it. A
    tag on a character entity fires the need-applicability sync (migration
    100), so the save needs the need-clock anchor first (``seed_story_clock``
    or ``seed_protagonist``).
    """

    require_disposable_target(dbname)
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        tag_id, category, entity_kind, category_deprecated = _resolve_bestowable_tag(
            cur, entity_id=entity_id, tag=tag
        )
        if category_deprecated is None:
            raise ValueError(
                f"tag {tag!r} is in category {category!r}, which "
                f"tag_category_registry does not register for {entity_kind} "
                "entities"
            )
        if category_deprecated:
            legacy_seed = (
                "seed_legacy_faction_tag"
                if entity_kind == "faction"
                else "seed_deprecated_category_tag"
            )
            raise ValueError(
                f"seed_entity_tag bestows only live categories: tag {tag!r} is in "
                f"the deprecated {entity_kind} category {category!r}; use "
                f"{legacy_seed} to plant legacy vocabulary"
            )
        cur.execute(
            """
            INSERT INTO entity_tags (entity_id, tag_id, source_kind)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (entity_id, tag_id, source_kind),
        )
        row = cur.fetchone()
        assert row is not None and cur.rowcount == 1
    return int(row[0])


def seed_routine_anchor(
    dbname: str,
    *,
    character_entity_id: int,
    place_id: int | None,
    anchor_type: str = "home",
    mobility_policy: str = "fixed_place",
    source: str = "test",
    schedule: Mapping[str, Any] | None = None,
) -> int:
    """Commit one routine anchor for a character entity; return the row ID.

    ``character_routine_anchors`` holds at most one row per
    ``(character_entity_id, anchor_type)``, so a second anchor of the same
    type for the same character fails on that unique key. The table's check
    constraints tie ``mobility_policy`` to its location: ``fixed_place`` needs
    ``place_id``; ``works_from_home``, ``nomadic``, and ``none`` need it NULL;
    ``zone_resolved`` needs a ``zone_id``, which this helper does not take, so
    it cannot seed that policy. The resolver reads these rows as actor sources
    and as ``at_routine_anchor`` evidence.
    """

    require_disposable_target(dbname)
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO character_routine_anchors (
                character_entity_id, anchor_type, place_id,
                mobility_policy, schedule, source
            ) VALUES (
                %s, %s::orrery_routine_anchor_type, %s,
                %s::orrery_routine_mobility_policy, %s::jsonb, %s
            )
            RETURNING id
            """,
            (
                character_entity_id,
                anchor_type,
                place_id,
                mobility_policy,
                json.dumps(dict(schedule or {})),
                source,
            ),
        )
        row = cur.fetchone()
        assert row is not None and cur.rowcount == 1
    return int(row[0])


def seed_pair_tag(
    dbname: str,
    *,
    subject_entity_id: int,
    object_entity_id: int,
    tag: str,
    source_kind: str = "template",
    template_id: str | None = None,
    source_chunk_id: int | None = None,
) -> int:
    """Commit one active directed pair tag; return the ``entity_pair_tags`` ID.

    ``tag`` must be a non-deprecated tag from the template's seeded
    ``pair_tags`` vocabulary; an unknown or deprecated tag fails the row-count
    assertion instead of inserting nothing. The row is active (``cleared_at``
    NULL), so the resolver, checkpoints, and ``entity_pair_tags`` readers see
    it from the next transaction on.
    """

    require_disposable_target(dbname)
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_pair_tags (
                subject_entity_id, object_entity_id, pair_tag_id,
                source_kind, template_id, source_chunk_id
            )
            SELECT %s, %s, pt.id, %s, %s, %s
            FROM pair_tags pt
            WHERE pt.tag = %s AND NOT pt.deprecated
            RETURNING id
            """,
            (
                subject_entity_id,
                object_entity_id,
                source_kind,
                template_id,
                source_chunk_id,
                tag,
            ),
        )
        row = cur.fetchone()
        assert row is not None and cur.rowcount == 1, f"pair tag {tag!r} is not seeded"
    return int(row[0])


# The TEST provider's registered model id; a fixture turn records it as the
# model that generated the staged prose, as the TEST seats do.
FIXTURE_GENERATION_MODEL = "TEST"


def seed_deprecated_category_tag(
    dbname: str,
    *,
    entity_id: int,
    tag: str,
) -> int:
    """Bestow a live tag in a deprecated non-faction category; return its ID.

    Clear-only coverage needs an active tag whose category the registry
    deprecates for the carrier's kind, such as ``worksite`` under migration
    043's ``place_affordance`` on a place. ``seed_entity_tag`` refuses those
    categories, so this helper plants them. It refuses a tag whose category is
    live or unregistered for the entity's kind, and it refuses faction entities
    outright: legacy faction vocabulary goes only through
    ``seed_legacy_faction_tag``. The row is active, so ``entity_tags_current``
    sees it.
    """

    require_disposable_target(dbname)
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        tag_id, category, entity_kind, category_deprecated = _resolve_bestowable_tag(
            cur, entity_id=entity_id, tag=tag
        )
        if entity_kind == "faction":
            raise ValueError(
                f"seed_deprecated_category_tag does not plant faction tags; use "
                f"seed_legacy_faction_tag for {tag!r} in {category!r}"
            )
        if category_deprecated is not True:
            raise ValueError(
                f"tag {tag!r} is in category {category!r}, which is not a "
                f"deprecated {entity_kind} category; use seed_entity_tag"
            )
        cur.execute(
            """
            INSERT INTO entity_tags (entity_id, tag_id, source_kind)
            VALUES (%s, %s, 'template')
            RETURNING id
            """,
            (entity_id, tag_id),
        )
        row = cur.fetchone()
        assert row is not None and cur.rowcount == 1
    return int(row[0])


def seed_legacy_faction_tag(
    dbname: str,
    *,
    faction_entity_id: int,
    category: str = "legitimacy_status",
    tag: str,
) -> int:
    """Bestow one tag in a migration-043 legacy faction category; return its ID.

    This is the one seed that plants a tag in a deprecated faction category,
    by construction: ``seed_entity_tag`` joins ``tag_category_registry`` on
    the tag's category and the entity's kind and raises on a deprecated
    category, and ``seed_deprecated_category_tag`` raises on any faction
    entity. Migration 043 deprecated seven faction categories
    (``LEGACY_TAG_CATEGORIES`` in ``nexus.api.faction_table_audit``) in
    ``tag_category_registry`` while their tags stayed readable through
    ``entity_tags_current``, and the faction table audit maps any such row it
    finds; this helper makes that audit non-vacuous on a clone. Any other
    category raises.

    The helper registers ``(category, 'faction')`` as deprecated if the clone
    lacks the row (043 leaves it deprecated), inserts the ``tags`` row if the
    tag is new (an existing tag must already sit in ``category``), and bestows
    it on the faction entity. It then asserts one registry row, one tag row,
    and exactly one ``entity_tags_current`` row for the bestowal.
    """

    require_disposable_target(dbname)
    from nexus.api.faction_table_audit import LEGACY_TAG_CATEGORIES

    if category not in LEGACY_TAG_CATEGORIES:
        raise ValueError(
            f"seed_legacy_faction_tag plants only migration-043 legacy faction "
            f"categories {LEGACY_TAG_CATEGORIES}, not {category!r}"
        )
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT kind::text FROM entities WHERE id = %s", (faction_entity_id,)
        )
        assert cur.fetchone() == (
            "faction",
        ), f"entity {faction_entity_id} is not a faction entity"
        cur.execute(
            """
            INSERT INTO tag_category_registry (
                category, entity_kind, description, deprecated
            ) VALUES (
                %s, 'faction'::entity_kind,
                'Legacy faction category deprecated by migration 043.', true
            )
            ON CONFLICT (category, entity_kind) DO NOTHING
            """,
            (category,),
        )
        cur.execute(
            "SELECT deprecated FROM tag_category_registry "
            "WHERE category = %s AND entity_kind = 'faction'",
            (category,),
        )
        assert cur.fetchall() == [
            (True,)
        ], f"migration 043 leaves the faction category {category!r} deprecated"
        cur.execute(
            """
            INSERT INTO tags (tag, category, description)
            VALUES (%s, %s, 'Legacy faction tag seeded for PostgreSQL coverage.')
            ON CONFLICT (tag) DO NOTHING
            """,
            (tag, category),
        )
        cur.execute(
            "SELECT id FROM tags WHERE tag = %s AND category = %s "
            "AND NOT deprecated AND synonym_for IS NULL",
            (tag, category),
        )
        tag_rows = cur.fetchall()
        assert (
            len(tag_rows) == 1
        ), f"tag {tag!r} is not a live tag in the legacy category {category!r}"
        cur.execute(
            """
            INSERT INTO entity_tags (entity_id, tag_id, source_kind)
            VALUES (%s, %s, 'template')
            RETURNING id
            """,
            (faction_entity_id, tag_rows[0][0]),
        )
        row = cur.fetchone()
        assert row is not None and cur.rowcount == 1
        cur.execute(
            """
            SELECT count(*) FROM entity_tags_current
            WHERE entity_tag_id = %s AND entity_id = %s
              AND entity_kind = 'faction' AND category = %s AND tag = %s
            """,
            (row[0], faction_entity_id, category, tag),
        )
        assert cur.fetchone()[0] == 1, "the legacy tag is not current"
    return int(row[0])


class AdjudicationLedgerSeed(NamedTuple):
    """The ledger ``seed_adjudication_ledger`` committed, by the rows it wrote.

    ``resolutions`` maps each resolution ID to its ``(promotion_status,
    narration_status)``; ``streaks`` maps each adjudicated proposal ID to
    ``(outcome, length)`` as ``adjudication_history`` names them
    (``ratified``, ``replace``, ``void``, ``open``).
    """

    tick_chunk_ids: tuple[int, ...]
    resolutions: Mapping[int, tuple[str, str]]
    adjudication_log_ids: tuple[int, ...]
    streaks: Mapping[str, tuple[str, int]]
    scene_pressure_ids: tuple[int, ...]
    prompt_exposure_ids: tuple[int, ...]


def seed_adjudication_ledger(
    dbname: str,
    *,
    actor_entity_id: int,
    ticks: tuple[int, ...] | list[int],
) -> AdjudicationLedgerSeed:
    """Commit a Skald ruling ledger over ``ticks``; return what it wrote.

    Every write goes through the production writers, as the Orrery cycle
    test does: one ``commit_orrery_tick_sync`` per tick with adjudications,
    then ``promote_pending_resolutions_sync`` and
    ``drain_narration_outbox_sync`` (deterministic descriptors; no provider
    call). ``ticks`` are two or more committed chunk IDs in ascending order;
    ``actor_entity_id`` is the character every draft binds as its actor.

    The committed ledger holds, for the adjudication history to read:

    - ``orrery_resolutions`` in every promotion status: on the first tick a
      salient draft (promoted, narration ``succeeded``) and a below-threshold
      draft (skipped, narration ``none``); on the second tick a draft
      ratified after a deferral and one committed by a replace with a delta
      (both pending, narration ``none``). The thresholds come from
      ``[orrery.promote]``.
    - ``orrery_adjudication_log`` defer streaks of every outcome: deferred on
      the first tick, then ratified, replaced, or voided on the second, and
      one draft deferred on every tick and never resolved (``open``).
    - One ``orrery_scene_pressures`` row per tick and the
      ``orrery_prompt_exposures`` rows for the drafts each tick renders under
      ``[orrery.prompt]``.

    The save must hold no pending resolution beforehand, so the promotion
    drain decides exactly the first tick's two rows. The committed rows are
    read back and asserted.
    """

    require_disposable_target(dbname)
    from nexus.agents.orrery.events import commit_orrery_tick_sync
    from nexus.agents.orrery.resolver import (
        OrreryResolutionDraft,
        OrreryScenePressureDraft,
        OrreryTickProposal,
    )
    from nexus.agents.orrery.worker import (
        drain_narration_outbox_sync,
        promote_pending_resolutions_sync,
    )

    tick_ids = tuple(int(tick) for tick in ticks)
    if len(tick_ids) < 2 or list(tick_ids) != sorted(set(tick_ids)):
        raise ValueError(
            "seed_adjudication_ledger needs two or more distinct ascending "
            f"tick chunk IDs, got {tick_ids!r}"
        )
    settings = load_settings()
    orrery = settings.require_orrery("the adjudication ledger fixture")
    orrery_settings = orrery.model_dump(by_alias=True)
    priority_threshold = orrery.promote.priority_threshold
    magnitude_threshold = orrery.promote.magnitude_threshold
    token = uuid.uuid4().hex[:12]

    def draft(
        template_id: str, role: str, *, priority: int, magnitude: float
    ) -> OrreryResolutionDraft:
        return OrreryResolutionDraft(
            template_id=template_id,
            priority=priority,
            binding_hash=f"ledger-{role}-{token}",
            bindings={"actor": actor_entity_id},
            branch_label=f"Ledger {role} fixture",
            narrative_stub=f"{{actor}} carries the ledger's {role} fixture.",
            magnitude=magnitude,
        )

    salient = int(priority_threshold) + 10
    quiet = max(int(priority_threshold) - 20, 0)
    promoted = draft("hide", "promoted", priority=salient, magnitude=0.9)
    skipped = draft(
        "stroll", "skipped", priority=quiet, magnitude=magnitude_threshold / 4
    )
    ratified = draft("eat", "ratified", priority=quiet, magnitude=0.1)
    replaced = draft("sleep", "replaced", priority=quiet, magnitude=0.1)
    voided = draft("drink", "voided", priority=quiet, magnitude=0.1)
    held_open = draft("work", "open", priority=quiet, magnitude=0.1)

    def pressure(tick: int) -> OrreryScenePressureDraft:
        return OrreryScenePressureDraft(
            template_id="sleep_need_pressure",
            priority=quiet,
            binding_hash=f"ledger-pressure-{tick}-{token}",
            bindings={"actor": actor_entity_id},
            branch_label="critical",
            pressure_stub="{actor} is running on fumes.",
            prompt_text="Someone is running on fumes.",
            magnitude=0.3,
        )

    def defer(item: OrreryResolutionDraft) -> dict[str, Any]:
        return {"proposal_id": item.proposal_id, "action": "defer"}

    first, second = tick_ids[0], tick_ids[1]
    plan: list[tuple[int, tuple[OrreryResolutionDraft, ...], list[dict[str, Any]]]]
    plan = [
        (
            first,
            (promoted, skipped, ratified, replaced, voided, held_open),
            [defer(ratified), defer(replaced), defer(voided), defer(held_open)],
        ),
        (
            second,
            (ratified, replaced, voided, held_open),
            [
                {
                    "proposal_id": replaced.proposal_id,
                    "action": "replace",
                    "note": "Ledger fixture: replaced after a deferral.",
                    "replacement_state_delta": {
                        "character.current_activity": "keeping a ledger fixture"
                    },
                },
                {
                    "proposal_id": voided.proposal_id,
                    "action": "void",
                    "note": "Ledger fixture: voided after a deferral.",
                },
                defer(held_open),
            ],
        ),
        *((tick, (held_open,), [defer(held_open)]) for tick in tick_ids[2:]),
    ]
    with closing(_connect(dbname)) as conn:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM narrative_chunks WHERE id = ANY(%s)",
                (list(tick_ids),),
            )
            assert cur.fetchone()[0] == len(
                tick_ids
            ), f"seed_adjudication_ledger ticks {tick_ids!r} are not all chunks"
            cur.execute(
                "SELECT count(*) FROM characters WHERE entity_id = %s",
                (actor_entity_id,),
            )
            assert (
                cur.fetchone()[0] == 1
            ), f"actor entity {actor_entity_id} is not a character"
            cur.execute(
                "SELECT count(*) FROM orrery_resolutions "
                "WHERE promotion_status = 'pending'"
            )
            assert cur.fetchone()[0] == 0, (
                "seed_adjudication_ledger needs a save with no pending "
                "resolution, so promotion decides only its own rows"
            )
        for tick, drafts, adjudications in plan:
            with conn:
                commit_orrery_tick_sync(
                    conn,
                    OrreryTickProposal(
                        anchor_chunk_id=tick,
                        actor_count=1,
                        resolutions=drafts,
                        scene_pressures=(pressure(tick),),
                    ),
                    tick_chunk_id=tick,
                    sunhelm_settings=orrery_settings.get("sunhelm"),
                    adjudications=adjudications,
                    prompt_settings=orrery_settings.get("prompt"),
                )
        assert promote_pending_resolutions_sync(
            limit=2, settings=settings, conn=conn
        ) == (1, 1), "the first tick's salient and quiet rows decide promotion"
        assert drain_narration_outbox_sync(settings=settings, conn=conn) == (
            1,
            0,
        ), "the promoted row's narration job completes"
        binding_hashes = [
            item.binding_hash
            for item in (promoted, skipped, ratified, replaced, voided, held_open)
        ]
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, binding_hash, tick_chunk_id,
                       promotion_status::text, narration_status::text
                FROM orrery_resolutions
                WHERE binding_hash = ANY(%s)
                ORDER BY id
                """,
                (binding_hashes,),
            )
            resolution_rows = cur.fetchall()
            cur.execute(
                """
                SELECT id, binding_hash, tick_chunk_id, action
                FROM orrery_adjudication_log
                WHERE binding_hash = ANY(%s)
                ORDER BY id
                """,
                (binding_hashes,),
            )
            log_rows = cur.fetchall()
            cur.execute(
                "SELECT id FROM orrery_scene_pressures "
                "WHERE tick_chunk_id = ANY(%s) AND binding_hash LIKE %s ORDER BY id",
                (list(tick_ids), f"ledger-pressure-%-{token}"),
            )
            pressure_ids = tuple(int(row[0]) for row in cur.fetchall())
            cur.execute(
                "SELECT id FROM orrery_prompt_exposures "
                "WHERE tick_chunk_id = ANY(%s) AND binding_hash LIKE %s ORDER BY id",
                (list(tick_ids), f"ledger-%-{token}"),
            )
            exposure_ids = tuple(int(row[0]) for row in cur.fetchall())
    committed = {
        (binding_hash, tick): (promotion, narration)
        for _id, binding_hash, tick, promotion, narration in resolution_rows
    }
    assert committed == {
        (promoted.binding_hash, first): ("promoted", "succeeded"),
        (skipped.binding_hash, first): ("skipped", "none"),
        (ratified.binding_hash, second): ("pending", "none"),
        (replaced.binding_hash, second): ("pending", "none"),
    }, f"seed_adjudication_ledger committed {resolution_rows!r}"
    rulings = [
        (binding_hash, tick, action) for _id, binding_hash, tick, action in log_rows
    ]
    expected_rulings = [
        (ratified.binding_hash, first, "defer"),
        (replaced.binding_hash, first, "defer"),
        (voided.binding_hash, first, "defer"),
        (held_open.binding_hash, first, "defer"),
        (replaced.binding_hash, second, "replace"),
        (voided.binding_hash, second, "void"),
        *((held_open.binding_hash, tick, "defer") for tick in tick_ids[1:]),
    ]
    assert sorted(rulings) == sorted(
        expected_rulings
    ), f"seed_adjudication_ledger logged {log_rows!r}"
    assert len(pressure_ids) == len(
        tick_ids
    ), f"seed_adjudication_ledger wrote pressures {pressure_ids!r}"
    assert exposure_ids, "seed_adjudication_ledger rendered no prompt exposure"
    return AdjudicationLedgerSeed(
        tick_chunk_ids=tick_ids,
        resolutions={
            int(row_id): (promotion, narration)
            for row_id, _hash, _tick, promotion, narration in resolution_rows
        },
        adjudication_log_ids=tuple(int(row[0]) for row in log_rows),
        streaks={
            ratified.proposal_id: ("ratified", 1),
            replaced.proposal_id: ("replace", 1),
            voided.proposal_id: ("void", 1),
            held_open.proposal_id: ("open", len(tick_ids)),
        },
        scene_pressure_ids=pressure_ids,
        prompt_exposure_ids=exposure_ids,
    )


def seed_adjudication_rulings(
    dbname: str,
    *,
    template_id: str,
    bindings: Mapping[str, int],
    rulings: tuple[tuple[int, str], ...] | list[tuple[int, str]],
) -> str:
    """Log Skald rulings on one uncommitted proposal; return its proposal ID.

    Each ``(tick_chunk_id, action)`` in ``rulings`` goes through the
    production log writer (``_insert_adjudication_log_sync``) with the
    ``explicit`` source, so every row is what a tick commit logs for that
    ruling, with ``actor_entity_id`` and ``bindings`` stamped. The binding
    hash is the resolver's ``binding_hash(bindings)``. Only ``defer`` and
    ``void`` are accepted: neither commits an ``orrery_resolutions`` row, so
    the rulings leave habituation (which debits only committed wins) and the
    resolver's selection unchanged. A replace commits a resolution through
    the tick writer; ``seed_adjudication_ledger`` covers that outcome.

    ``rulings`` must be in ascending tick order over committed chunks, and
    ``bindings["actor"]`` must be a character.
    """

    require_disposable_target(dbname)
    from nexus.agents.orrery.events import (
        OrreryAdjudicationDecision,
        _insert_adjudication_log_sync,
    )
    from nexus.agents.orrery.resolver import OrreryResolutionDraft
    from nexus.agents.orrery.substrate import Slot, binding_hash

    ticks = [int(tick) for tick, _action in rulings]
    if not rulings or ticks != sorted(ticks):
        raise ValueError(
            "seed_adjudication_rulings needs one or more rulings in ascending "
            f"tick order, got {rulings!r}"
        )
    refused = sorted({action for _tick, action in rulings} - {"defer", "void"})
    if refused:
        raise ValueError(
            f"seed_adjudication_rulings logs only defer and void, got {refused!r}"
        )
    if "actor" not in bindings:
        raise ValueError(
            f"seed_adjudication_rulings needs an actor binding, got {bindings!r}"
        )
    # Key the hash input by Slot, as the resolver does; an unknown slot name
    # raises here rather than hashing a binding no template can carry.
    slot_bindings = {Slot(slot): value for slot, value in bindings.items()}
    draft = OrreryResolutionDraft(
        template_id=template_id,
        priority=0,
        binding_hash=binding_hash(slot_bindings),
        bindings=dict(bindings),
        branch_label="Seeded ruling",
        narrative_stub="{actor} waits on a seeded ruling.",
        magnitude=0.1,
    )
    with closing(_connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM narrative_chunks WHERE id = ANY(%s)",
            (sorted(set(ticks)),),
        )
        assert cur.fetchone()[0] == len(
            set(ticks)
        ), f"seed_adjudication_rulings ticks {ticks!r} are not all chunks"
        cur.execute(
            "SELECT count(*) FROM characters WHERE entity_id = %s",
            (int(bindings["actor"]),),
        )
        assert (
            cur.fetchone()[0] == 1
        ), f"actor entity {bindings['actor']} is not a character"
        for tick, action in rulings:
            _insert_adjudication_log_sync(
                cur,
                draft,
                OrreryAdjudicationDecision(
                    proposal_id=draft.proposal_id,
                    action=action,
                    note=f"Seeded {action} ruling.",
                ),
                tick_chunk_id=int(tick),
                adjudication_source="explicit",
            )
        cur.execute(
            "SELECT tick_chunk_id, action FROM orrery_adjudication_log "
            "WHERE proposal_id = %s ORDER BY tick_chunk_id, id",
            (draft.proposal_id,),
        )
        logged = [(int(tick), action) for tick, action in cur.fetchall()]
    assert logged == [
        (int(tick), action) for tick, action in rulings
    ], f"seed_adjudication_rulings logged {logged!r}"
    return draft.proposal_id


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
    pass a slot only while ``route_slots_to_disposable`` (directly, or through
    ``tests.scheduler_helpers.route_slot``) routes that slot to the clone; any
    other routing would reach an owner database.

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


def _remembered_chunks(cur: Any, parent_chunk_id: int) -> list[tuple[int, str]]:
    """Return the committed playable chunks up to the parent, oldest first."""

    from nexus.agents.orrery.reconstruction import playable_narrative_predicate

    cur.execute(
        "SELECT nc.id, nc.storyteller_text FROM narrative_chunks nc WHERE "
        + playable_narrative_predicate()
        + " AND nc.id <= %s ORDER BY nc.id",
        (parent_chunk_id,),
    )
    return [(int(chunk_id), str(text)) for chunk_id, text in cur.fetchall()]


def _remembered_pass2_baseline(
    settings: Any, *, storyteller_text: str, remembered: list[tuple[int, str]]
) -> Any:
    """Build a remembering Pass-2 baseline the way a played turn exports one.

    Pass 1 of a continuation holds the committed chunks up to its parent in
    its warm slice. The production ``ContextMemoryManager`` stores that
    baseline from this turn's prose, the warm slice, and the turn's token
    counts (``total_available`` is the story's storyteller window, the warm
    slice is each remembered chunk's estimated tokens), and exports it with
    ``export_pass2_baseline``: every remembered chunk ID as a memory
    identity, the token accounting with the manager's derived entries, and a
    positive remaining budget. Returns the unbound ``Pass2BaselineV2``.
    """

    from nexus.memory.manager import ContextMemoryManager

    if not remembered:
        raise ValueError("a remembering Pass-2 baseline needs a committed chunk")
    window = settings.lore.token_budget.apex_context_window
    if not isinstance(window, int) or window <= 0:
        raise RuntimeError(
            "a remembering Pass-2 baseline needs a resolved apex_context_window, "
            f"got {window!r}"
        )
    manager = ContextMemoryManager(settings)
    warm_tokens = sum(manager._estimate_tokens(text) for _, text in remembered)
    manager.handle_storyteller_response(
        storyteller_text,
        warm_slice=[
            {"chunk_id": chunk_id, "text": text} for chunk_id, text in remembered
        ],
        token_usage={
            "total_available": window,
            "warm_slice": warm_tokens,
            "structured": 0,
            "augmentation": 0,
        },
    )
    baseline = manager.export_pass2_baseline()
    assert baseline.memory_identities == [chunk_id for chunk_id, _ in remembered]
    assert baseline.prior_token_accounting and baseline.remaining_budget > 0, (
        "the remembering baseline has no token accounting or remaining budget: "
        f"{baseline.prior_token_accounting!r}, {baseline.remaining_budget!r}"
    )
    return baseline


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
    remembered_baseline: bool = False,
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

    ``remembered_baseline`` stages instead the baseline a played
    continuation exports (``_remembered_pass2_baseline``): the committed
    chunks up to the parent as memory identities, token accounting, and a
    positive remaining budget. The bootstrap opening refuses it, since
    ``generate_bootstrap_narrative`` stages the empty baseline.

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
            if remembered_baseline:
                if parent_chunk_id == 0:
                    raise ValueError(
                        "seed_pending_turn stages the empty baseline for the "
                        "bootstrap opening; remembered_baseline needs a "
                        "committed parent"
                    )
                baseline = _remembered_pass2_baseline(
                    settings,
                    storyteller_text=storyteller_text,
                    remembered=_remembered_chunks(cur, parent_chunk_id),
                )
            else:
                baseline = empty_pass2_baseline(settings)
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
    base_timestamp: str = DEFAULT_BASE_TIMESTAMP,
    time_delta: timedelta = timedelta(minutes=5),
    cast: tuple[str, ...] = (),
    correspondence: bool = False,
    slot: int | None = None,
    remembered_baselines: bool = False,
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

    ``remembered_baselines`` stages each continuation with the Pass-2
    baseline a played turn exports (``seed_pending_turn``'s
    ``remembered_baseline``): the committed chunks before it as memory
    identities, token accounting, and a positive remaining budget, bound to
    the accepted chunk at commit. The bootstrap opening keeps the empty
    baseline, as in play. By default every turn stages the empty baseline.

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
                remembered_baseline=remembered_baselines and turn > 1,
            )
        )
        user_text = FIXTURE_TURN_CHOICES[0]
    return chunk_ids


# The off-screen cast ``seed_starved_story`` mentions in every turn.
STARVED_STORY_CAST = ("Mara Quill", "Oren Vale")


def seed_starved_story(dbname: str, *, slot: int) -> list[int]:
    """Play a story whose scene reset leaves experience renders queued.

    Four accepted turns six story hours apart, with ``STARVED_STORY_CAST``
    off-screen and writer and Gaia letters on every turn, then a
    scene-boundary turn one hour later, all through ``seed_played_story``
    and ``seed_accepted_turn``. The scene reset is the production path that
    enqueues ``character_experience_jobs``: the accepting commit inserts the
    cast's experience seeds and one render batch per scene. Returns the IDs
    of the render jobs the reset enqueued, in order.

    Every returned job is queued and resolved to the TEST model through the
    clone's TEST story pin (``disposable_slot_database`` pins clones to TEST),
    so a scheduler that renders it reaches only the TEST provider; the helper
    asserts both. ``slot`` must route to ``dbname``.
    """

    require_disposable_target(dbname)
    _require_slot_routes_to(dbname, slot)
    seed_played_story(
        dbname,
        turns=4,
        cast=STARVED_STORY_CAST,
        time_delta=timedelta(hours=6),
        correspondence=True,
        slot=slot,
    )
    boundary = seed_accepted_turn(
        dbname,
        user_text=FIXTURE_TURN_CHOICES[0],
        storyteller_text="The scene resets as the plaza empties for the night.",
        choices=list(FIXTURE_TURN_CHOICES),
        choice_text=FIXTURE_TURN_CHOICES[0],
        scene_boundary=True,
        time_delta=timedelta(hours=1),
        correspondence_writer_letter="Writer note for the scene reset.",
        correspondence_gaia_letter="Gaia note for the scene reset.",
        slot=slot,
    )
    with closing(_connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, state::text, resolved_model FROM character_experience_jobs "
            "WHERE boundary_chunk_id = %s ORDER BY id",
            (boundary,),
        )
        jobs = cur.fetchall()
    assert jobs, "The scene reset enqueued no experience render jobs"
    assert all(
        (state, model) == ("queued", FIXTURE_GENERATION_MODEL)
        for _, state, model in jobs
    ), f"seed_starved_story enqueued jobs that are not queued on TEST: {jobs!r}"
    return [int(job_id) for job_id, _, _ in jobs]


class ExperienceCandidatesSeed(NamedTuple):
    """The scene chunk and actors ``seed_experience_candidates`` seeded."""

    scene_end_chunk_id: int
    actor_entity_ids: list[int]


class ExperienceRenderJobSeed(NamedTuple):
    """The queued render job ``seed_experience_render_job`` enqueued."""

    job_id: int
    experience_ids: list[int]
    scene_end_chunk_id: int
    boundary_chunk_id: int


def _insert_experience_chunk(cur: Any, label: str) -> int:
    """Insert one primary-layer chunk stamped at the save's ``base_timestamp``."""

    cur.execute(
        "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
        "VALUES (%s, %s) RETURNING id",
        (label, label),
    )
    assert cur.rowcount == 1
    chunk_id = int(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO chunk_metadata "
        "(chunk_id, season, episode, scene, world_layer, slug) "
        "VALUES (%s, 1, 1, %s, 'primary', %s)",
        (chunk_id, chunk_id, f"qa677_{chunk_id}"),
    )
    assert cur.rowcount == 1
    cur.execute(
        "UPDATE chunk_metadata SET world_time = gv.base_timestamp "
        "FROM global_variables gv "
        "WHERE gv.id = true AND chunk_metadata.chunk_id = %s",
        (chunk_id,),
    )
    assert cur.rowcount == 1
    return chunk_id


def _insert_experience_actor(
    cur: Any,
    name: str,
    *,
    summary: str | None,
    background: str | None,
) -> tuple[int, int]:
    """Insert one character with its entity; return character and entity IDs."""

    cur.execute("INSERT INTO entities (kind) VALUES ('character') RETURNING id")
    assert cur.rowcount == 1
    entity_id = int(cur.fetchone()[0])
    cur.execute(
        """
        INSERT INTO characters (name, entity_id, summary, background)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (name, entity_id, summary, background),
    )
    assert cur.rowcount == 1
    return int(cur.fetchone()[0]), entity_id


def seed_experience_candidates(
    dbname: str,
    *,
    settings: Settings,
    label: str,
    seed_count: int = 2,
) -> ExperienceCandidatesSeed:
    """Seed ``seed_count`` actors' experience candidates at one scene chunk.

    In one transaction it inserts a scene chunk at ``base_timestamp``,
    ``seed_count`` actors, a ``slept`` event for each and its actor row in
    ``world_event_entities``. Then it runs the production experience sweep
    (``seed_character_experiences_sync``) anchored at that chunk and asserts
    one seed per actor. The save needs a story clock and a player
    (``seed_protagonist``); without a clock it fails by name.
    """

    from nexus.agents.orrery.experiences import seed_character_experiences_sync

    require_disposable_target(dbname)
    with closing(_connect(dbname)) as conn:
        with conn, conn.cursor() as cur:
            _require_need_clock_anchor(cur, "seed_experience_candidates")
            scene_end_chunk_id = _insert_experience_chunk(cur, f"{label} scene")
            actor_entity_ids: list[int] = []
            for ordinal in range(seed_count):
                _character_id, entity_id = _insert_experience_actor(
                    cur,
                    f"{label} Actor {ordinal}",
                    summary=f"{label} actor {ordinal} has a complete dossier.",
                    background="Present for a verified event role.",
                )
                actor_entity_ids.append(entity_id)
                cur.execute(
                    """
                    INSERT INTO world_events (
                        event_type, tick_chunk_id, actor_entity_id,
                        world_layer, source, changed_fields, payload
                    ) VALUES (
                        'slept', %s, %s, 'primary', 'resolver',
                        '{}', '{}'::jsonb
                    ) RETURNING id
                    """,
                    (scene_end_chunk_id, entity_id),
                )
                assert cur.rowcount == 1
                event_id = int(cur.fetchone()[0])
                cur.execute(
                    """
                    INSERT INTO world_event_entities (event_id, entity_id, role)
                    VALUES (%s, %s, 'actor')
                    """,
                    (event_id, entity_id),
                )
                assert cur.rowcount == 1
        with conn:
            seeded = seed_character_experiences_sync(
                conn,
                anchor_chunk_id=scene_end_chunk_id,
                settings=settings,
            )
        assert seeded == seed_count, (
            f"seed_experience_candidates expected {seed_count} experience "
            f"seeds at chunk {scene_end_chunk_id}, got {seeded}"
        )
    return ExperienceCandidatesSeed(scene_end_chunk_id, actor_entity_ids)


def seed_experience_render_job(
    dbname: str,
    *,
    settings: Settings,
    label: str,
    slot: int,
    seed_count: int = 2,
) -> ExperienceRenderJobSeed:
    """Seed experience candidates, then enqueue their scene's render job.

    Calls ``seed_experience_candidates``, inserts a boundary chunk, and runs
    the production scene-reset enqueue (``enqueue_scene_experience_job_sync``)
    for ``slot``, asserting exactly one job. Returns that job's ID and its
    ``experience_ids``, read by the boundary chunk.
    """

    from nexus.agents.orrery.experiences import enqueue_scene_experience_job_sync

    require_disposable_target(dbname)
    candidates = seed_experience_candidates(
        dbname, settings=settings, label=label, seed_count=seed_count
    )
    with closing(_connect(dbname)) as conn:
        with conn, conn.cursor() as cur:
            boundary_chunk_id = _insert_experience_chunk(cur, f"{label} boundary")
            enqueued = enqueue_scene_experience_job_sync(
                conn,
                boundary_chunk_id=boundary_chunk_id,
                scene_end_chunk_id=candidates.scene_end_chunk_id,
                world_layer="primary",
                slot=slot,
                settings=settings,
            )
            assert enqueued == 1, (
                f"seed_experience_render_job expected one render job at "
                f"boundary {boundary_chunk_id}, got {enqueued}"
            )
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, experience_ids FROM character_experience_jobs "
                "WHERE boundary_chunk_id = %s",
                (boundary_chunk_id,),
            )
            rows = cur.fetchall()
    assert len(rows) == 1, rows
    job_id, experience_ids = rows[0]
    return ExperienceRenderJobSeed(
        job_id=int(job_id),
        experience_ids=[int(value) for value in experience_ids],
        scene_end_chunk_id=candidates.scene_end_chunk_id,
        boundary_chunk_id=boundary_chunk_id,
    )
