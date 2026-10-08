"""Story identity: minted at birth, renewed per story, forked on clone (#822).

Requires ``NEXUS_RUN_POSTGRES=1``. Every database is a disposable clone from
``tests/pg_fixtures.py``; no owner database is written.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
import re
import uuid

import psycopg2
from psycopg2 import errors, sql
import pytest

from nexus.api.new_story_db_mapper import NewStoryDatabaseMapper
from nexus.api.story_identity import (
    detach_clone_identity,
    read_story_uuid,
    record_fork,
    replace_story_identity,
)
from nexus.config import load_settings
from nexus.runtime.readiness import (
    ReadinessContext,
    _check_slot_story_identity,
    _check_template_story_identity,
)
from scripts import backfill_story_identity as backfill
from scripts import migrate, new_story_setup
from tests.pg_fixtures import (
    connect,
    disposable_database,
    disposable_slot_database,
    route_slot_to_disposable,
    route_slots_to_disposable,
)
from tests.test_orrery.test_need_clock_anchor_pg import _build_story_transition

pytestmark = pytest.mark.requires_postgres

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "146_story_identity.sql"
)
TEMPLATE_REMEDIATION = (
    "Delete it: NEXUS_template carries no story identity "
    "(psql -d NEXUS_template -c 'DELETE FROM public.story_identity')"
)


def _identity(dbname: str) -> list[tuple[str, str]]:
    """Every ``(story_uuid, origin)`` row of ``dbname``."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT story_uuid::text, origin FROM public.story_identity")
        return cur.fetchall()


def _lineage(dbname: str) -> list[tuple[str, str, str, str, str]]:
    """Every lineage row of ``dbname``, without its timestamp."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "SELECT child_uuid::text, parent_uuid::text, relation, source_dbname, "
            "evidence FROM public.story_lineage ORDER BY parent_uuid"
        )
        return cur.fetchall()


def _execute(dbname: str, statement: str, params: tuple = ()) -> None:
    """Run one statement in its own committed transaction."""
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(statement, params)


def _set_read_only(dbname: str, on: bool) -> None:
    """Lock or unlock ``dbname`` the way a locked save slot is locked."""
    setting = (
        "SET default_transaction_read_only = on"
        if on
        else "RESET default_transaction_read_only"
    )
    admin = connect("postgres")
    admin.autocommit = True
    with closing(admin), admin.cursor() as cur:
        cur.execute(
            sql.SQL("ALTER DATABASE {} " + setting).format(sql.Identifier(dbname))
        )


@contextmanager
def _locked(dbname: str) -> Iterator[None]:
    """Hold ``dbname`` locked, unlocking it before its fixture drops it."""
    _set_read_only(dbname, True)
    try:
        yield
    finally:
        _set_read_only(dbname, False)


def test_initialization_mints_one_identity() -> None:
    """A fresh slot database holds one version-4 ``wizard`` identity, no lineage."""
    with disposable_slot_database("qa640_822_init") as dbname:
        ((story_uuid, origin),) = _identity(dbname)
        assert origin == "wizard"
        assert uuid.UUID(story_uuid).version == 4
        assert _lineage(dbname) == []


def test_reset_mints_a_new_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each forced initialization recreates the database and mints a new value."""
    monkeypatch.setattr(new_story_setup, "USE_POOL", False)
    with disposable_slot_database("qa640_822_reset_src") as source:
        # A template stand-in: the template carries the table and no row.
        _execute(source, "DELETE FROM public.story_identity")
        with disposable_database("qa640_822_reset") as dbname:
            values = []
            for _ in range(2):
                new_story_setup.initialize_slot_database(
                    dbname, source_db=source, force=True
                )
                ((story_uuid, origin),) = _identity(dbname)
                assert origin == "wizard"
                values.append(story_uuid)
            assert values[0] != values[1]


def test_transition_renews_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every wizard transition mints a new identity and drops the old lineage."""
    with disposable_slot_database("qa640_822_transition") as dbname:
        route_slot_to_disposable(monkeypatch.setattr, slot=3, dbname=dbname)
        ((initial, _),) = _identity(dbname)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            record_fork(
                cur,
                child_uuid=initial,
                parent_uuid=str(uuid.uuid4()),
                source_dbname="qa640_822_parent",
                evidence="a lineage row the transition must drop",
            )
        assert len(_lineage(dbname)) == 1
        values = [initial]
        for _ in range(2):
            # Each transition clears the wizard cache after commit, and the
            # next trait persistence needs the cache row, so build each time.
            transition = _build_story_transition(dbname)
            NewStoryDatabaseMapper(dbname=dbname).perform_transition(transition)
            ((story_uuid, origin),) = _identity(dbname)
            assert origin == "wizard"
            assert _lineage(dbname) == []
            values.append(story_uuid)
        assert len(set(values)) == 3


def test_clone_forks_with_lineage(monkeypatch: pytest.MonkeyPatch) -> None:
    """A data clone gets a new ``clone`` identity and one fork row to its source."""
    monkeypatch.setattr(new_story_setup, "USE_POOL", False)
    with disposable_slot_database("qa640_822_clone_src") as source:
        ((source_uuid, _),) = _identity(source)
        grandparent = str(uuid.uuid4())
        with closing(connect(source)) as conn, conn, conn.cursor() as cur:
            record_fork(
                cur,
                child_uuid=source_uuid,
                parent_uuid=grandparent,
                source_dbname="qa640_822_grandparent",
                evidence="the source's own parent",
            )
        source_lineage = _lineage(source)
        with disposable_database("qa640_822_clone") as target:
            new_story_setup.clone_slot_with_data(
                5, source_db=source, force=True, target_db=target
            )
            ((child, origin),) = _identity(target)
            assert origin == "clone"
            assert child != source_uuid
            assert _lineage(target) == [
                (
                    child,
                    source_uuid,
                    "fork",
                    source,
                    f"clone_slot_with_data copied {source} into {target}",
                )
            ]
        assert _identity(source) == [(source_uuid, "wizard")]
        assert _lineage(source) == source_lineage

        # A source without a row (the template, an unbackfilled database).
        _execute(source, "DELETE FROM public.story_identity")
        with disposable_database("qa640_822_clone_bare") as target:
            new_story_setup.clone_slot_with_data(
                5, source_db=source, force=True, target_db=target
            )
            ((_, origin),) = _identity(target)
            assert origin == "clone"
            assert _lineage(target) == []

        # An invalid source is refused before --force can erase an existing
        # destination. Keep the traceback alive to also catch leaked connections.
        _execute(
            source,
            "ALTER TABLE public.story_identity "
            "DROP CONSTRAINT story_identity_id_check; "
            "INSERT INTO public.story_identity (id, origin) "
            "VALUES (TRUE, 'wizard'), (FALSE, 'wizard')",
        )
        with disposable_database("qa640_822_clone_invalid") as target:
            _execute(target, "CREATE TABLE previous_story (content text)")
            _execute(target, "INSERT INTO previous_story VALUES ('keep this story')")
            with pytest.raises(RuntimeError, match="2 story_identity rows"):
                new_story_setup.clone_slot_with_data(
                    5, source_db=source, force=True, target_db=target
                )
            with closing(connect(target)) as conn, conn, conn.cursor() as cur:
                cur.execute("SELECT content FROM previous_story")
                assert cur.fetchall() == [("keep this story",)]

        _execute(source, "DROP TABLE public.story_lineage, public.story_identity")
        with disposable_database("qa640_822_clone_pre146") as target:
            _execute(target, "CREATE TABLE previous_story (content text)")
            _execute(target, "INSERT INTO previous_story VALUES ('keep this story')")
            with pytest.raises(RuntimeError, match="scripts/migrate.py") as refused:
                new_story_setup.clone_slot_with_data(
                    5, source_db=source, force=True, target_db=target
                )
            # ``refused`` still holds the traceback and so the failing frames.
            assert refused.value is not None
            with closing(connect(target)) as conn, conn, conn.cursor() as cur:
                cur.execute("SELECT content FROM previous_story")
                assert cur.fetchall() == [("keep this story",)]
            with closing(connect(source)) as conn, conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = %s",
                    (target,),
                )
                assert cur.fetchone()[0] == 0


def _migration_comments() -> dict[str, str]:
    """Each ``COMMENT ON`` target in migration 146 and its text."""
    found = re.findall(
        r"^COMMENT ON (TABLE|COLUMN) public\.(\S+) IS '((?:[^']|'')*)';$",
        MIGRATION.read_text(),
        flags=re.M,
    )
    return {target: text.replace("''", "'") for _, target, text in found}


def test_migration_146_creates_empty_tables() -> None:
    """The runner creates both tables with their comments and no row."""
    with disposable_slot_database("qa640_822_migration") as dbname:
        _execute(
            dbname,
            "DROP TABLE public.story_lineage, public.story_identity; "
            "DELETE FROM public.schema_migrations WHERE version = '146'",
        )
        assert migrate.migrate_database(dbname, skip_locked=False) == (1, 0)
        expected = _migration_comments()
        assert len(expected) == 2 + 5 + 6
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            for table in ("story_identity", "story_lineage"):
                cur.execute(f"SELECT count(*) FROM public.{table}")
                assert cur.fetchone()[0] == 0
                cur.execute(
                    "SELECT obj_description(%s::regclass, 'pg_class')",
                    (f"public.{table}",),
                )
                assert cur.fetchone()[0] == expected.pop(table)
            for target, text in expected.items():
                table, column = target.split(".")
                cur.execute(
                    "SELECT col_description(%s::regclass, attnum) "
                    "FROM pg_attribute WHERE attrelid = %s::regclass "
                    "AND attname = %s",
                    (f"public.{table}", f"public.{table}", column),
                )
                assert cur.fetchone()[0] == text, target


def test_identity_constraints() -> None:
    """The singleton, origin, relation and self-parent rules are enforced."""
    with disposable_slot_database("qa640_822_constraints") as dbname:
        ((story_uuid, _),) = _identity(dbname)
        with pytest.raises(errors.UniqueViolation):
            _execute(
                dbname, "INSERT INTO public.story_identity (origin) VALUES ('wizard')"
            )
        with pytest.raises(errors.CheckViolation):
            _execute(
                dbname,
                "INSERT INTO public.story_identity (id, origin) "
                "VALUES (false, 'wizard')",
            )
        with pytest.raises(errors.CheckViolation):
            _execute(dbname, "UPDATE public.story_identity SET origin = 'other'")
        lineage = (
            "INSERT INTO public.story_lineage "
            "(child_uuid, parent_uuid, relation, source_dbname, evidence) "
            "VALUES (%s, %s, %s, 'qa640_822_parent', 'e')"
        )
        with pytest.raises(errors.CheckViolation):
            _execute(dbname, lineage, (story_uuid, str(uuid.uuid4()), "merge"))
        with pytest.raises(errors.CheckViolation):
            _execute(dbname, lineage, (story_uuid, story_uuid, "fork"))
        assert _lineage(dbname) == []


def test_backfill_mints_and_links(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backfill mints once, links once, refuses locks, wizard rows and the template."""
    with (
        disposable_slot_database("qa640_822_backfill_a") as a,
        disposable_slot_database("qa640_822_backfill_b") as b,
        disposable_slot_database("qa640_822_backfill_t") as stand_in,
    ):
        for dbname in (a, b, stand_in):
            _execute(dbname, "DELETE FROM public.story_identity")
        forks = [backfill.ForkSpec(b, a, "e")]

        # A fork whose child is not a target is refused before any write.
        with pytest.raises(ValueError, match="is not a backfill target"):
            backfill.backfill_story_identity([a], forks)
        assert _identity(a) == []
        assert _identity(b) == []

        minted = backfill.backfill_story_identity([a, b], forks)
        assert _identity(a) == [(minted[a], "backfill")]
        assert _identity(b) == [(minted[b], "backfill")]
        assert _lineage(b) == [(minted[b], minted[a], "fork", a, "e")]
        assert _lineage(a) == []
        assert backfill.backfill_story_identity([a, b], forks) == minted
        assert _lineage(b) == [(minted[b], minted[a], "fork", a, "e")]

        # A child that already forks another parent is never relinked.
        _execute(
            stand_in, "INSERT INTO public.story_identity (origin) VALUES ('backfill')"
        )
        with pytest.raises(RuntimeError, match="already forks"):
            backfill.backfill_story_identity([b], [backfill.ForkSpec(b, stand_in, "e")])
        assert _lineage(b) == [(minted[b], minted[a], "fork", a, "e")]
        _execute(stand_in, "DELETE FROM public.story_identity")

        for dbname in (a, b):
            _execute(dbname, "DELETE FROM public.story_identity")
        with _locked(a):
            with pytest.raises(ValueError, match="--write-locked-slot"):
                backfill.backfill_story_identity([a, b], forks)
            assert _identity(a) == []
            assert _identity(b) == []
            minted = backfill.backfill_story_identity(
                [a, b], forks, write_locked_slot=True
            )
            assert migrate.is_db_locked(a)
            assert _identity(a) == [(minted[a], "backfill")]
            assert _lineage(b) == [(minted[b], minted[a], "fork", a, "e")]

        with closing(connect(b)) as conn, conn, conn.cursor() as cur:
            replace_story_identity(cur, origin="wizard")
        with pytest.raises(ValueError, match="two backfill identities"):
            backfill.backfill_story_identity([a, b], forks)
        assert _lineage(b) == []

        monkeypatch.setattr(migrate, "TEMPLATE_DB", stand_in)
        before = _identity(a)
        with pytest.raises(ValueError, match="carries no story identity"):
            backfill.backfill_story_identity([a, stand_in], [])
        with pytest.raises(ValueError, match="never a fork's child or parent"):
            backfill.backfill_story_identity([a], [backfill.ForkSpec(a, stand_in, "e")])
        assert _identity(stand_in) == []
        assert _identity(a) == before


@pytest.mark.parametrize(
    "problem, message",
    [
        ("missing_identity", "scripts/migrate.py"),
        ("missing_lineage", "scripts/migrate.py"),
        ("empty_parent", "0 story_identity rows"),
        ("wizard_parent", "two backfill identities"),
        ("wizard_child", "two backfill identities"),
        ("different_parent", "already forks"),
        ("multiple_identities", "2 story_identity rows"),
        ("self_parent", "self-parentage"),
        ("conflicting_parents", "conflicting requested parents"),
    ],
)
def test_backfill_preflights_all_databases(problem: str, message: str) -> None:
    """A later target or fork refusal leaves every earlier target unminted."""
    with (
        disposable_slot_database("qa640_822_preflight_a") as a,
        disposable_slot_database("qa640_822_preflight_b") as b,
        disposable_slot_database("qa640_822_preflight_parent") as parent,
    ):
        for dbname in (a, b, parent):
            _execute(dbname, "DELETE FROM public.story_identity")
        _execute(
            parent, "INSERT INTO public.story_identity (origin) VALUES ('backfill')"
        )
        forks = [backfill.ForkSpec(b, parent, "existing parent")]
        if problem == "missing_identity":
            _execute(b, "DROP TABLE public.story_lineage, public.story_identity")
        elif problem == "missing_lineage":
            _execute(b, "DROP TABLE public.story_lineage")
        elif problem == "empty_parent":
            _execute(parent, "DELETE FROM public.story_identity")
        elif problem == "wizard_parent":
            _execute(parent, "UPDATE public.story_identity SET origin = 'wizard'")
        elif problem == "wizard_child":
            _execute(b, "INSERT INTO public.story_identity (origin) VALUES ('wizard')")
        elif problem == "different_parent":
            _execute(
                b, "INSERT INTO public.story_identity (origin) VALUES ('backfill')"
            )
            with closing(connect(b)) as conn, conn, conn.cursor() as cur:
                record_fork(
                    cur,
                    child_uuid=read_story_uuid(cur),
                    parent_uuid=str(uuid.uuid4()),
                    source_dbname="qa640_822_previous_parent",
                    evidence="an existing relationship must not be overwritten",
                )
        elif problem == "multiple_identities":
            _execute(
                b,
                "ALTER TABLE public.story_identity "
                "DROP CONSTRAINT story_identity_id_check; "
                "INSERT INTO public.story_identity (id, origin) "
                "VALUES (TRUE, 'backfill'), (FALSE, 'backfill')",
            )
        elif problem == "self_parent":
            forks = [backfill.ForkSpec(b, b, "invalid self-parent")]
        elif problem == "conflicting_parents":
            forks.append(backfill.ForkSpec(b, a, "conflicting parent"))

        before_b = _identity(b) if problem != "missing_identity" else None
        before_parent = _identity(parent)
        with pytest.raises((ValueError, RuntimeError), match=message):
            backfill.backfill_story_identity([a, b], forks)
        assert _identity(a) == []
        if before_b is not None:
            assert _identity(b) == before_b
        assert _identity(parent) == before_parent


def _doctor_context(slots: list[int]) -> ReadinessContext:
    """A readiness context whose ``[runtime.readiness].slots`` is ``slots``."""
    settings = load_settings()
    assert settings.runtime is not None
    readiness = settings.runtime.readiness.model_copy(update={"slots": slots})
    runtime = settings.runtime.model_copy(update={"readiness": readiness})
    return ReadinessContext(settings=settings.model_copy(update={"runtime": runtime}))


def test_doctor_identity_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each registered template and slot identity check names its exact remediation.

    The template check reads ``scripts.migrate.TEMPLATE_DB`` at call time and
    the slot check resolves each ``[runtime.readiness].slots`` number through
    ``slot_dbname``, so a patched template name and routed slots carry both
    registered checks to disposable clones.
    """
    ctx = _doctor_context([3, 4])
    with disposable_slot_database("qa640_822_doctor_t") as template:
        monkeypatch.setattr(migrate, "TEMPLATE_DB", template)
        outcome = _check_template_story_identity(ctx)
        assert (outcome.passed, outcome.observed, outcome.remediation) == (
            False,
            f"{template}: 1 story_identity row(s)",
            TEMPLATE_REMEDIATION,
        )
        _execute(template, "DELETE FROM public.story_identity")
        outcome = _check_template_story_identity(ctx)
        assert (outcome.passed, outcome.observed) == (
            True,
            f"{template}: no story identity row",
        )
        _execute(template, "DROP TABLE public.story_lineage, public.story_identity")
        outcome = _check_template_story_identity(ctx)
        assert (outcome.passed, outcome.observed, outcome.remediation) == (
            False,
            f"{template}: no story_identity table (migration 146 pending)",
            "python scripts/migrate.py --template",
        )

    with disposable_slot_database("qa640_822_doctor_s") as dbname:
        # Slot 4 routes to a name the server lacks: reported, never failed.
        absent = f"{dbname}_absent"
        route_slots_to_disposable(monkeypatch.setattr, {3: dbname, 4: absent})
        outcome = _check_slot_story_identity(ctx)
        assert (outcome.passed, outcome.observed) == (
            True,
            f"{dbname}: one story identity row; {absent} absent",
        )
        _execute(dbname, "DELETE FROM public.story_identity")
        outcome = _check_slot_story_identity(ctx)
        assert (outcome.passed, outcome.observed, outcome.remediation) == (
            False,
            f"{dbname}: no story identity row; {absent} absent",
            "python scripts/backfill_story_identity.py --slot 3",
        )
        with _locked(dbname):
            outcome = _check_slot_story_identity(ctx)
            assert (outcome.passed, outcome.remediation) == (
                False,
                "python scripts/backfill_story_identity.py --slot 3 "
                "--write-locked-slot",
            )
        _execute(dbname, "DROP TABLE public.story_lineage, public.story_identity")
        outcome = _check_slot_story_identity(ctx)
        assert (outcome.passed, outcome.observed, outcome.remediation) == (
            False,
            f"{dbname}: no story_identity table (migration 146 pending); "
            f"{absent} absent",
            "python scripts/migrate.py --slot 3",
        )
        with _locked(dbname):
            outcome = _check_slot_story_identity(ctx)
            assert (outcome.passed, outcome.remediation) == (
                False,
                "python scripts/migrate.py --slot 3 --write-locked-slot",
            )


def test_disposable_clones_detach_identity() -> None:
    """A data clone of a minted source gets a fresh ``clone`` row and no lineage."""
    with disposable_slot_database("qa640_822_detach_src") as source:
        ((source_uuid, _),) = _identity(source)
        with closing(connect(source)) as conn, conn, conn.cursor() as cur:
            record_fork(
                cur,
                child_uuid=source_uuid,
                parent_uuid=str(uuid.uuid4()),
                source_dbname="qa640_822_parent",
                evidence="the source's own parent",
            )
        with disposable_slot_database(
            "qa640_822_detach", source_db=source, include_data=True
        ) as clone:
            ((clone_uuid, origin),) = _identity(clone)
            assert origin == "clone"
            assert clone_uuid != source_uuid
            assert _lineage(clone) == []
            with closing(connect(clone)) as conn, conn, conn.cursor() as cur:
                assert read_story_uuid(cur) == clone_uuid
        assert _identity(source) == [(source_uuid, "wizard")]
    for owner in ("save_01", "NEXUS_template"):
        with pytest.raises(ValueError, match="refuses"):
            detach_clone_identity(owner)


def test_detach_requires_migration_146() -> None:
    """A clone without the table raises; the detach is never skipped."""
    with disposable_slot_database("qa640_822_detach_bare") as dbname:
        _execute(dbname, "DROP TABLE public.story_lineage, public.story_identity")
        with pytest.raises(psycopg2.errors.UndefinedTable):
            detach_clone_identity(dbname)
