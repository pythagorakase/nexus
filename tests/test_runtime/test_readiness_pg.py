"""PostgreSQL readiness checks (issue #803) against a real NEXUS server.

Requires ``NEXUS_RUN_POSTGRES=1`` and a server holding ``NEXUS_template``.
Stamp edits happen only on a disposable template clone that the fixture
drops; the owner's template and slots are only read.
"""

from __future__ import annotations

from contextlib import closing

import psycopg2
import pytest

from nexus.api.slot_utils import slot_dbname
from nexus.config import load_settings
from nexus.database import connection_kwargs, connection_target
from nexus.runtime.readiness import (
    REGISTRY,
    REQUIRED_EXTENSIONS,
    ReadinessContext,
    read_only_connection,
    database_migration_state,
    run_readiness,
)
from scripts import migrate
from tests import pg_fixtures

pytestmark = pytest.mark.requires_postgres

DATABASE_CHECKS = {
    "config.valid",
    "postgres.reachable",
    "postgres.extensions",
    "template.present",
    "template.migrations_current",
    "slots.migrations_current",
}


def test_owner_host_database_checks_run_against_the_contract_server() -> None:
    """The server, its extensions and the template pass; migrations are read."""
    registry = [spec for spec in REGISTRY if spec.id in DATABASE_CHECKS]
    report = run_readiness("owner-host", ReadinessContext(), registry=registry)
    checks = {check.id: check for check in report.checks}

    target = connection_target(connection_kwargs("postgres"))
    reachable = checks["postgres.reachable"]
    assert reachable.status == "pass"
    assert reachable.observed.startswith(f"{target['user']}@")
    assert f":{target['port']}/postgres: PostgreSQL " in reachable.observed

    extensions = checks["postgres.extensions"]
    assert extensions.status == "pass"
    assert [part.split()[0] for part in extensions.observed.split(", ")] == list(
        REQUIRED_EXTENSIONS
    )
    assert checks["template.present"].status == "pass"

    template = checks["template.migrations_current"]
    assert template.status in {"pass", "fail"}
    assert template.observed.startswith("NEXUS_template")
    if template.status == "fail":
        assert "python scripts/migrate.py --template" in (
            template.remediation or ""
        ) or "git pull" in (template.remediation or "")

    slots = checks["slots.migrations_current"]
    assert slots.status in {"pass", "fail"}
    settings = load_settings()
    assert settings.runtime is not None
    for slot in settings.runtime.readiness.slots:
        assert slot_dbname(slot) in slots.observed


def test_migration_state_compares_stamps_with_this_checkout() -> None:
    """Pending, unknown and untracked stamps are each named, read-only."""
    discovered = migrate.discover_migrations()
    latest = discovered[-1][0]
    with pg_fixtures.disposable_slot_database("readiness803") as dbname:
        state = database_migration_state(dbname, discovered)
        assert state.current
        assert state.describe() == f"{dbname} at {latest}"

        with closing(pg_fixtures.connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM schema_migrations WHERE version = %s", (latest,))
            cur.execute(
                "INSERT INTO schema_migrations (version, name) "
                "VALUES ('999', 'from_a_newer_checkout')"
            )
        state = database_migration_state(dbname, discovered)
        assert (state.pending, state.unknown, state.current) == (
            [latest],
            ["999"],
            False,
        )
        assert state.describe() == (
            f"{dbname}: 1 pending ({latest}), 1 unknown to this checkout (999)"
        )

        with closing(pg_fixtures.connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DROP TABLE schema_migrations")
        state = database_migration_state(dbname, discovered)
        assert state.tracked is False
        assert len(state.pending) == len(discovered)
        assert state.describe().startswith(
            f"{dbname}: no schema_migrations stamps, {len(discovered)} pending ("
        )


def test_readiness_sessions_refuse_writes() -> None:
    """The session every database check reads through cannot write."""
    with pg_fixtures.disposable_slot_database("readiness803ro") as dbname:
        with closing(read_only_connection(dbname)) as conn, conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
                cur.execute("CREATE TABLE readiness_write_probe (id integer)")
