"""Offline coverage for the stamped-without-vector embedding audit (#848).

The audit's counting query runs on SQLite, a real SQL engine, through a thin
dialect shim that answers PostgreSQL's ``to_regclass`` from ``sqlite_master``
and swaps ``%s`` placeholders for ``?``. The PostgreSQL proofs live in
``tests/test_orrery/test_retrograde_embedding_pg.py`` and
``tests/test_jobs_cli_pg.py``.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterator

import pytest

from nexus import cli
from nexus.agents.memnon.utils.source_embeddings import (
    AUDITED_SOURCES,
    CHARACTER_EXPERIENCE_SOURCE,
    RETROGRADE_SUMMARY_SOURCE,
    count_stamped_without_vectors,
)

MODELS = {"alpha": 3, "beta": 5}


class _SqliteCursor:
    """DBAPI cursor over SQLite that speaks the audit's PostgreSQL."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._cursor = connection.cursor()

    def execute(self, statement: str, params: Any = ()) -> None:
        if statement.startswith("SELECT to_regclass(%s)"):
            self._cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = ?)",
                (params[0].removeprefix("public."),),
            )
            return
        self._cursor.execute(statement.replace("%s", "?"), params)

    def fetchone(self) -> Any:
        return self._cursor.fetchone()


@pytest.fixture()
def database() -> Iterator[sqlite3.Connection]:
    """Two stamped summaries, one unstamped, and one stamped experience."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE retrograde_summaries (
            id INTEGER PRIMARY KEY, embedding_generated_at TEXT
        );
        INSERT INTO retrograde_summaries VALUES
            (1, '2196-01-01'), (2, '2196-01-01'), (3, NULL);
        CREATE TABLE character_experiences (
            id INTEGER PRIMARY KEY, embedding_generated_at TEXT
        );
        INSERT INTO character_experiences VALUES (7, '2196-01-01');
        """
    )
    yield connection
    connection.close()


def _count(connection: sqlite3.Connection, source: Any = None) -> int:
    return count_stamped_without_vectors(
        _SqliteCursor(connection), source or RETROGRADE_SUMMARY_SOURCE, MODELS
    )


def _add_vectors(
    connection: sqlite3.Connection, table: str, fk: str, rows: list[tuple[int, str]]
) -> None:
    connection.execute(f"CREATE TABLE IF NOT EXISTS {table} ({fk} INTEGER, model TEXT)")
    connection.executemany(f"INSERT INTO {table} VALUES (?, ?)", rows)


def test_missing_dimension_table_counts_every_stamped_row(
    database: sqlite3.Connection,
) -> None:
    """With no vector table at all, every stamp is unbacked; NULL is pending."""
    assert _count(database) == 2
    assert _count(database, CHARACTER_EXPERIENCE_SOURCE) == 1


def test_one_missing_active_model_is_enough(database: sqlite3.Connection) -> None:
    """A row counts until every active model's vector exists."""
    _add_vectors(
        database,
        "retrograde_summary_embeddings_0003d",
        "summary_id",
        [(1, "alpha"), (2, "alpha"), (3, "alpha")],
    )
    assert _count(database) == 2

    _add_vectors(
        database,
        "retrograde_summary_embeddings_0005d",
        "summary_id",
        [(1, "beta"), (2, "dormant")],
    )
    assert _count(database) == 1

    _add_vectors(
        database, "retrograde_summary_embeddings_0005d", "summary_id", [(2, "beta")]
    )
    assert _count(database) == 0
    assert _count(database, CHARACTER_EXPERIENCE_SOURCE) == 1


def test_audit_covers_both_source_owned_corpora() -> None:
    """The jobs payload audits exactly the summary and experience corpora."""
    assert [source.table for source in AUDITED_SOURCES] == [
        "retrograde_summaries",
        "character_experiences",
    ]


def _jobs_payload(stamped_without_vectors: dict[str, int]) -> dict[str, Any]:
    return {
        "scheduler": None,
        "queues": {},
        "non_terminal_jobs": [],
        "unembedded_accepted_chunks": 0,
        "stamped_without_vectors": stamped_without_vectors,
    }


def test_jobs_output_names_damage_only_when_present(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`nexus jobs` prints the audit line only for a nonzero count."""
    cli._print_jobs(
        _jobs_payload({"retrograde_summaries": 0, "character_experiences": 0})
    )
    assert "stamped_without_vectors" not in capsys.readouterr().out

    cli._print_jobs(
        _jobs_payload({"retrograde_summaries": 12, "character_experiences": 0})
    )
    assert capsys.readouterr().out.splitlines()[-1] == (
        "stamped_without_vectors: retrograde_summaries=12, character_experiences=0"
    )


def test_jobs_output_refuses_a_pre_upgrade_payload() -> None:
    """A gateway older than the CLI is named, not papered over with a default."""
    payload = _jobs_payload({"retrograde_summaries": 0, "character_experiences": 0})
    del payload["stamped_without_vectors"]
    with pytest.raises(RuntimeError, match="stamped_without_vectors.*restart"):
        cli._print_jobs(payload)
