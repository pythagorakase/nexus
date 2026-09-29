"""Seed helpers refuse the owner's databases before they connect.

``tests.pg_fixtures.require_disposable_target`` refuses ``NEXUS_template`` and
every save slot by name, and each seed helper calls it before it opens a
connection. An owner-slot seed is always a test bug, so there is no override.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, NoReturn

import psycopg2
import pytest

from tests import pg_fixtures
from tests.pg_fixtures import connect, require_disposable_target, seed_entity_tag
from tests.test_orrery.checkpointed_story_support import seed_checkpointed_story

OWNER_DATABASES = (
    "save_01",
    "save_02",
    "save_03",
    "save_04",
    "save_05",
    "NEXUS_template",
)

# Every guarded helper with valid keyword arguments. The guard runs first, so
# none of these values reaches a database.
SEED_CALLS: dict[str, tuple[Callable[..., Any], dict[str, Any]]] = {
    "seed_protagonist": (pg_fixtures.seed_protagonist, {}),
    "seed_committed_chunk": (
        pg_fixtures.seed_committed_chunk,
        {"raw_text": "Refused."},
    ),
    "seed_story_clock": (
        pg_fixtures.seed_story_clock,
        {"world_time": datetime(2073, 8, 1, 12, 0, tzinfo=timezone.utc)},
    ),
    "seed_zone": (
        pg_fixtures.seed_zone,
        {
            "name": "Refused Zone",
            "min_longitude": -1.0,
            "min_latitude": -1.0,
            "max_longitude": 1.0,
            "max_latitude": 1.0,
        },
    ),
    "seed_place": (pg_fixtures.seed_place, {"name": "Refused Place"}),
    "seed_character": (pg_fixtures.seed_character, {"name": "Refused Character"}),
    "seed_faction": (pg_fixtures.seed_faction, {"name": "Refused Faction"}),
    "seed_relationship": (
        pg_fixtures.seed_relationship,
        {
            "subject_character_id": 1,
            "object_character_id": 2,
            "relationship_type": "ally",
        },
    ),
    "seed_entity_tag": (
        pg_fixtures.seed_entity_tag,
        {"entity_id": 1, "tag": "kin_protector"},
    ),
    "seed_checkpointed_story": (seed_checkpointed_story, {}),
}


def _refuse_connection(*args: object, **kwargs: object) -> NoReturn:
    """Fail the test the moment a seed helper dials PostgreSQL."""

    pytest.fail(
        "A seed helper opened a PostgreSQL connection before refusing its target.",
        pytrace=False,
    )


@pytest.mark.parametrize("dbname", OWNER_DATABASES)
def test_require_disposable_target_refuses_owner_databases(dbname: str) -> None:
    """Each save slot and the template raise, and the error names the database."""

    with pytest.raises(RuntimeError, match=re.escape(repr(dbname))):
        require_disposable_target(dbname)


def test_require_disposable_target_returns_a_disposable_name() -> None:
    """A disposable clone name passes through unchanged."""

    assert require_disposable_target("qa640_x") == "qa640_x"


def test_seed_calls_cover_every_seed_helper() -> None:
    """A new seed helper must join ``SEED_CALLS``, which proves its guard."""

    defined = {
        name
        for name, function in inspect.getmembers(pg_fixtures, inspect.isfunction)
        if name.startswith("seed_") and function.__module__ == pg_fixtures.__name__
    }
    assert defined | {"seed_checkpointed_story"} == set(SEED_CALLS)


@pytest.mark.parametrize("helper", sorted(SEED_CALLS))
def test_seed_helpers_refuse_owner_databases_before_connecting(
    helper: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each helper raises on every owner name without dialing PostgreSQL.

    The test installs the ``psycopg2.connect`` tripwire that the conftest
    applies offline, in both gates, so a helper that lost its guard fails here
    instead of reaching an owner database.
    """

    monkeypatch.setattr(psycopg2, "connect", _refuse_connection)
    seed, arguments = SEED_CALLS[helper]
    for dbname in OWNER_DATABASES:
        with pytest.raises(RuntimeError, match=re.escape(repr(dbname))):
            seed(dbname, **arguments)


def _sessions(cur: Any, dbname: str) -> int:
    """Return how many sessions PostgreSQL has established to ``dbname``."""

    cur.execute("SELECT sessions FROM pg_stat_database WHERE datname = %s", (dbname,))
    row = cur.fetchone()
    assert row is not None, f"pg_stat_database has no row for {dbname}"
    return int(row[0])


@pytest.mark.requires_postgres
def test_seed_helper_refuses_save_05_before_connecting() -> None:
    """A seed aimed at ``save_05`` raises before the server sees a session.

    ``pg_stat_activity`` lists only open backends, and a helper closes its
    connection before an exception leaves it, so the check reads the
    cumulative ``pg_stat_database.sessions``, which counts a session before
    ``connect`` returns; the control connection proves the counter moves. The
    call could not write even without its guard: no tag matches, so the
    ``INSERT ... SELECT`` would insert nothing.
    """

    with closing(connect("postgres")) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            control_before = _sessions(cur, "postgres")
            connect("postgres").close()
            assert _sessions(cur, "postgres") > control_before, (
                "pg_stat_database.sessions did not count a new connection, so "
                "an unchanged save_05 count would prove nothing"
            )
            before = _sessions(cur, "save_05")
            with pytest.raises(RuntimeError, match=re.escape(repr("save_05"))):
                seed_entity_tag("save_05", entity_id=0, tag="no_such_tag")
            after = _sessions(cur, "save_05")
    assert after == before, (
        f"PostgreSQL recorded {after - before} new save_05 session(s) during a "
        "refused seed"
    )
