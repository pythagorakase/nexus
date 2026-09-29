"""PostgreSQL readiness checks (issue #803) against a real NEXUS server.

Requires ``NEXUS_RUN_POSTGRES=1`` and a server holding ``NEXUS_template``.
Stamp edits happen only on a disposable template clone that the fixture
drops; the owner's template and slots are only read.
"""

from __future__ import annotations

from contextlib import closing

import psycopg2
from psycopg2 import sql
import pytest

from nexus.agents.memnon.utils.idf_dictionary import REBUILD_COMMAND
from nexus.api.save_slots import is_slot_locked
from nexus.api.slot_utils import slot_dbname
from nexus.config import load_settings
from nexus.database import connection_kwargs, connection_target
from nexus.runtime.readiness import (
    REGISTRY,
    REQUIRED_EXTENSIONS,
    ReadinessContext,
    read_only_connection,
    database_analyzer_state,
    database_migration_state,
    run_readiness,
    slot_idf_outcome,
)
from scripts import migrate, rebuild_memory_idf
from tests import pg_fixtures

pytestmark = pytest.mark.requires_postgres

DATABASE_CHECKS = {
    "config.valid",
    "postgres.reachable",
    "postgres.extensions",
    "template.present",
    "template.migrations_current",
    "slots.migrations_current",
    "template.idf_analyzer_current",
    "slots.idf_analyzer_current",
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

    template_idf = checks["template.idf_analyzer_current"]
    assert template_idf.status in {"pass", "fail"}
    assert template_idf.observed.startswith("NEXUS_template")
    if template_idf.status == "fail":
        assert f"{REBUILD_COMMAND} --template" in (
            template_idf.remediation or ""
        ) or "python scripts/migrate.py --template" in (template_idf.remediation or "")

    slots_idf = checks["slots.idf_analyzer_current"]
    assert slots_idf.status in {"pass", "fail"}
    for slot in settings.runtime.readiness.slots:
        assert slot_dbname(slot) in slots_idf.observed
    if slots_idf.status == "fail":
        assert REBUILD_COMMAND in (slots_idf.remediation or "") or (
            "python scripts/migrate.py --slot" in (slots_idf.remediation or "")
        )
    existing = _existing_databases(
        [slot_dbname(slot) for slot in settings.runtime.readiness.slots]
    )
    for slot in settings.runtime.readiness.slots:
        dbname = slot_dbname(slot)
        if dbname not in existing or not is_slot_locked(slot):
            continue
        state = database_analyzer_state(dbname)
        if state.tracked and state.stale:
            assert slots_idf.status == "fail"
            assert state.describe() in slots_idf.observed
            assert f"{REBUILD_COMMAND} --slot {slot} --write-locked-slot" in (
                (slots_idf.remediation or "").split("; ")
            )


def _existing_databases(names: list[str]) -> set[str]:
    """The subset of ``names`` the contract server holds."""
    with closing(read_only_connection("postgres")) as conn, conn.cursor() as cur:
        cur.execute("SELECT datname FROM pg_database WHERE datname = ANY(%s)", (names,))
        return {row[0] for row in cur.fetchall()}


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


def test_idf_analyzer_check_names_the_stale_corpus_until_rebuilt() -> None:
    """The registered slot check fails on a stale key, naming the fix, until rebuilt.

    ``slot_idf_outcome`` is the body of ``slots.idf_analyzer_current`` after
    the probed slots are named, so the clone stands in for slot 9 through the
    same existence lookup, lock probe, and remediation commands.
    """
    with pg_fixtures.disposable_slot_database("qa640_1013_readiness") as dbname:
        pg_fixtures.seed_protagonist(dbname)
        pg_fixtures.seed_committed_chunk(dbname, raw_text="Gulls circle the pier.")
        names = {9: dbname}
        state = database_analyzer_state(dbname)
        server = state.server_key
        assert state.current
        assert state.corpora == {"narrative": server, "retrograde_summary": server}
        outcome = slot_idf_outcome(names)
        assert (outcome.passed, outcome.observed) == (True, f"{dbname} at {server}")

        with closing(pg_fixtures.connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE memory_idf_corpora SET analyzer_version = %s "
                "WHERE corpus_kind = 'narrative'",
                ("pg_catalog.english/v1/0",),
            )
        stale_observed = (
            f"{dbname}: narrative pg_catalog.english/v1/0 (server {server})"
        )
        outcome = slot_idf_outcome(names)
        assert outcome.passed is False
        assert outcome.observed == stale_observed
        assert outcome.remediation == f"{REBUILD_COMMAND} --slot 9"

        _set_read_only(dbname, True)
        try:
            outcome = slot_idf_outcome(names)
            assert outcome.passed is False
            assert outcome.observed == stale_observed
            assert outcome.remediation == (
                f"{REBUILD_COMMAND} --slot 9 --write-locked-slot"
            )
        finally:
            _set_read_only(dbname, False)

        assert rebuild_memory_idf.rebuild_database(dbname).status == "rebuilt"
        outcome = slot_idf_outcome(names)
        assert (outcome.passed, outcome.observed) == (True, f"{dbname} at {server}")

        absent = f"{dbname}_absent"
        outcome = slot_idf_outcome({9: dbname, 8: absent})
        assert (outcome.passed, outcome.observed) == (
            True,
            f"{dbname} at {server}; {absent} absent",
        )

        # Past migration 114 a missing table is a missing corpus set.
        with closing(pg_fixtures.connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DROP TABLE memory_idf_corpora CASCADE")
        outcome = slot_idf_outcome(names)
        assert outcome.passed is False
        assert outcome.observed == (
            f"{dbname}: no memory_idf_corpora table though migration 114 is "
            "applied (missing corpora narrative and retrograde_summary)"
        )
        assert outcome.remediation == f"{REBUILD_COMMAND} --slot 9"

        # Before migration 114 the runner installs the table.
        with closing(pg_fixtures.connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM schema_migrations WHERE version = '114'")
            assert cur.rowcount == 1
        outcome = slot_idf_outcome(names)
        assert outcome.passed is False
        assert outcome.observed == (
            f"{dbname}: no memory_idf_corpora table (migration 114 pending)"
        )
        assert outcome.remediation == "python scripts/migrate.py --slot 9"


def _drop_corpus_rows(dbname: str, *kinds: str) -> None:
    """Delete corpus rows and the projection rows that reference them."""
    with closing(pg_fixtures.connect(dbname)) as conn, conn, conn.cursor() as cur:
        for table in (
            "memory_idf_lexemes",
            "memory_idf_documents",
            "memory_idf_corpora",
        ):
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE corpus_kind = ANY(%s)").format(
                    sql.Identifier(table)
                ),
                (list(kinds),),
            )


def test_idf_analyzer_check_fails_on_missing_corpus_rows_until_rebuilt() -> None:
    """A missing corpus row fails the registered slot check until the tool seeds it.

    Zero rows fail too; only both rows at the server's key pass.
    """
    with pg_fixtures.disposable_slot_database("qa640_1013_readiness") as dbname:
        pg_fixtures.seed_protagonist(dbname)
        pg_fixtures.seed_committed_chunk(dbname, raw_text="Gulls circle the pier.")
        names = {9: dbname}
        server = database_analyzer_state(dbname).server_key

        _drop_corpus_rows(dbname, "narrative")
        outcome = slot_idf_outcome(names)
        assert outcome.passed is False
        assert outcome.observed == f"{dbname}: missing corpus narrative"
        assert outcome.remediation == f"{REBUILD_COMMAND} --slot 9"
        with pytest.raises(psycopg2.errors.NoDataFound):
            pg_fixtures.seed_committed_chunk(
                dbname, raw_text="The pier refuses this write.", scene=2
            )

        assert rebuild_memory_idf.main(["--dbname", dbname]) == 0
        state = database_analyzer_state(dbname)
        assert state.corpora == {"narrative": server, "retrograde_summary": server}
        outcome = slot_idf_outcome(names)
        assert (outcome.passed, outcome.observed) == (True, f"{dbname} at {server}")
        pg_fixtures.seed_committed_chunk(
            dbname, raw_text="The tide takes the pier.", scene=2
        )

        _drop_corpus_rows(dbname, "narrative", "retrograde_summary")
        assert database_analyzer_state(dbname).corpora == {}
        outcome = slot_idf_outcome(names)
        assert outcome.passed is False
        assert outcome.observed == (
            f"{dbname}: missing corpora narrative and retrograde_summary"
        )
        assert outcome.remediation == f"{REBUILD_COMMAND} --slot 9"


def _set_read_only(dbname: str, on: bool) -> None:
    """Lock or unlock ``dbname`` the way a locked save slot is locked."""
    setting = (
        "SET default_transaction_read_only = on"
        if on
        else ("RESET default_transaction_read_only")
    )
    admin = pg_fixtures.connect("postgres")
    admin.autocommit = True
    with closing(admin), admin.cursor() as cur:
        cur.execute(
            sql.SQL("ALTER DATABASE {} " + setting).format(sql.Identifier(dbname))
        )


def test_readiness_sessions_refuse_writes() -> None:
    """The session every database check reads through cannot write."""
    with pg_fixtures.disposable_slot_database("readiness803ro") as dbname:
        with closing(read_only_connection(dbname)) as conn, conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
                cur.execute("CREATE TABLE readiness_write_probe (id integer)")
