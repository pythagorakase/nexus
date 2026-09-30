"""PostgreSQL proofs for ``nexus tags audit`` (issue #811) on template clones.

Every database here is a disposable ``NEXUS_template`` clone. The audit reads
the owner's slots only through the CLI's ``--all`` proof in
``docs/qa/811-tags-audit/verification.md``, never from this suite.
"""

from __future__ import annotations

from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
import sys
from typing import Any, Iterator

import pytest
from psycopg2 import sql

from nexus import cli
from nexus.api import deprecated_tag_audit
from nexus.api.deprecated_tag_audit import DeprecatedTagAuditError, audit_database
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_entity_tag,
    seed_faction,
)

pytestmark = pytest.mark.requires_postgres


@pytest.fixture
def audited_clone() -> Iterator[tuple[str, dict[str, int]]]:
    """A template clone holding active, cleared, and live-category faction tags.

    Two factions carry ``gray_legal`` (deprecated ``legitimacy_status``,
    replaced by ``legitimacy``); one carries ``ancient_continuous``
    (deprecated ``history_class``, no replacement), a cleared
    ``criminal_underground`` (deprecated, but no longer active), and
    ``contested`` (the live ``legitimacy`` category).
    """
    with disposable_slot_database("qa640_811_tags_audit") as dbname:
        _, first = seed_faction(dbname, name="Lantern Syndicate")
        _, second = seed_faction(dbname, name="Tidewater Compact")
        for entity_id, tag in (
            (first, "gray_legal"),
            (second, "gray_legal"),
            (first, "ancient_continuous"),
            (first, "criminal_underground"),
            (first, "contested"),
        ):
            seed_entity_tag(dbname, entity_id=entity_id, tag=tag)
        with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE entity_tags SET cleared_at = now()
                WHERE entity_id = %s
                  AND tag_id = (SELECT id FROM tags WHERE tag = 'criminal_underground')
                """,
                (first,),
            )
            assert cur.rowcount == 1
        yield dbname, {"first": first, "second": second}


def _expected_groups(entities: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "category": "history_class",
            "tag": "ancient_continuous",
            "replacement_categories": [],
            "row_count": 1,
            "entity_ids": [entities["first"]],
        },
        {
            "category": "legitimacy_status",
            "tag": "gray_legal",
            "replacement_categories": ["legitimacy"],
            "row_count": 2,
            "entity_ids": sorted([entities["first"], entities["second"]]),
        },
    ]


def _run_main(monkeypatch: pytest.MonkeyPatch, *argv: str) -> tuple[int, str, str]:
    """Run the real CLI entry point in process and capture both streams."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        monkeypatch.context() as patch,
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        patch.setattr(sys, "argv", ["nexus", *argv])
        code = cli.main()
    return code, stdout.getvalue(), stderr.getvalue()


def _route_slot_three(monkeypatch: pytest.MonkeyPatch, dbname: str) -> None:
    """Point the audit's slot 3 at the clone; every other slot is refused."""

    def slot_database(slot: int) -> str:
        if slot != 3:
            raise AssertionError(f"The audit read slot {slot}, not the clone")
        return dbname

    monkeypatch.setattr(deprecated_tag_audit, "slot_dbname", slot_database)
    monkeypatch.setattr(deprecated_tag_audit, "all_slots", lambda: [3])


def test_audit_reports_active_rows_in_deprecated_categories(audited_clone) -> None:
    """Only active rows whose category the registry deprecates are reported."""
    dbname, entities = audited_clone

    report = audit_database(dbname)

    assert report["database"] == dbname
    assert report["slot"] is None
    assert {"history_class", "legitimacy_status", "place_affordance"} <= set(
        report["deprecated_categories"]
    )
    assert "legitimacy" not in report["deprecated_categories"]
    assert report["groups"] == _expected_groups(entities)
    assert report["active_rows"] == 3


def test_tags_audit_cli_prints_the_envelope_and_the_table(
    audited_clone, monkeypatch
) -> None:
    """``nexus tags audit --slot N`` wraps the report in the success envelope."""
    dbname, entities = audited_clone
    _route_slot_three(monkeypatch, dbname)

    code, stdout, stderr = _run_main(
        monkeypatch, "tags", "audit", "--slot", "3", "--json"
    )
    assert (code, stderr) == (0, "")
    envelope = json.loads(stdout)
    assert envelope["ok"] is True
    assert envelope["data"]["active_rows"] == 3
    (database,) = envelope["data"]["databases"]
    assert (database["database"], database["slot"]) == (dbname, 3)
    assert database["groups"] == _expected_groups(entities)

    code, stdout, stderr = _run_main(monkeypatch, "tags", "audit", "--slot", "3")
    assert (code, stderr) == (0, "")
    lines = stdout.splitlines()
    assert lines[0].split() == ["DATABASE", "ROWS"]
    assert lines[1].split() == [dbname, "3"]
    assert lines[3].split() == [
        "DATABASE",
        "CATEGORY",
        "TAG",
        "ROWS",
        "ENTITIES",
        "REPLACEMENTS",
    ]
    assert lines[5].split() == [
        dbname,
        "legitimacy_status",
        "gray_legal",
        "2",
        ",".join(str(i) for i in sorted(entities.values())),
        "legitimacy",
    ]
    assert lines[4].split()[-1] == "-"


def test_audit_reads_a_locked_database_without_writing(audited_clone) -> None:
    """A slot locked read-only is audited like any other; nothing changes."""
    dbname, entities = audited_clone
    with closing(connect(dbname)) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "ALTER DATABASE {} SET default_transaction_read_only = on"
                ).format(sql.Identifier(dbname))
            )
            cur.execute("SELECT count(*), max(id) FROM entity_tags")
            before = cur.fetchone()

    report = audit_database(dbname)

    assert report["groups"] == _expected_groups(entities)
    with closing(connect(dbname)) as conn, conn.cursor() as cur:
        cur.execute("SHOW default_transaction_read_only")
        assert cur.fetchone() == ("on",)
        cur.execute("SELECT count(*), max(id) FROM entity_tags")
        assert cur.fetchone() == before


def test_audit_without_the_registry_schema_names_the_migration(
    audited_clone, monkeypatch
) -> None:
    """A missing registry column or table is a loud failure naming its migration."""
    dbname, _ = audited_clone
    _route_slot_three(monkeypatch, dbname)
    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE tag_category_registry DROP COLUMN replacement_categories"
        )
    with pytest.raises(
        DeprecatedTagAuditError,
        match=(
            "has no tag_category_registry.replacement_categories column; apply "
            "migration 043_orrery_category_refactor_phase1"
        ),
    ):
        audit_database(dbname)

    with closing(connect(dbname)) as conn, conn, conn.cursor() as cur:
        cur.execute("DROP TABLE tag_category_registry CASCADE")
    code, stdout, stderr = _run_main(
        monkeypatch, "tags", "audit", "--slot", "3", "--json"
    )

    assert (code, stdout) == (1, "")
    envelope = json.loads(stderr)
    assert envelope["ok"] is False
    assert envelope["code"] == "domain_failure"
    assert envelope["error"] == (
        f"{dbname} has no tag_category_registry table; apply migration "
        "037_orrery_tag_category_registry (scripts/migrate.py) before auditing it"
    )


def test_all_audit_missing_an_entity_tags_column_keeps_the_partial(
    audited_clone, monkeypatch
) -> None:
    """A later database without ``entity_tags.cleared_at`` is a domain failure.

    ``--all`` reads the template first; here the template is the intact clone
    and slot 3 is a second clone with the column dropped. The preflight names
    the migration, and the envelope's ``partial`` keeps the template's report,
    instead of the audit statement leaking PostgreSQL's ``UndefinedColumn``.
    """
    dbname, entities = audited_clone
    with disposable_slot_database("qa640_811_tags_audit_nocol") as broken:
        with closing(connect(broken)) as conn, conn, conn.cursor() as cur:
            cur.execute("ALTER TABLE entity_tags DROP COLUMN cleared_at CASCADE")
        monkeypatch.setattr(deprecated_tag_audit, "TEMPLATE_DATABASE", dbname)
        _route_slot_three(monkeypatch, broken)

        with pytest.raises(
            DeprecatedTagAuditError,
            match="has no entity_tags.cleared_at column",
        ):
            audit_database(broken)

        code, stdout, stderr = _run_main(
            monkeypatch, "tags", "audit", "--all", "--json"
        )

    assert (code, stdout) == (1, "")
    envelope = json.loads(stderr)
    assert envelope["ok"] is False
    assert envelope["code"] == "domain_failure"
    assert envelope["error"] == (
        f"{broken} has no entity_tags.cleared_at column; apply migration "
        "023_orrery_schema (scripts/migrate.py) before auditing it"
    )
    (template_report,) = envelope["partial"]["databases"]
    assert template_report["database"] == dbname
    assert template_report["groups"] == _expected_groups(entities)
