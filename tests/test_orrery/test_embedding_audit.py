"""Offline coverage for the embedding audit (#848) and experience backlog (#754).

The audit's counting query and the experience drain's selection run on
SQLite, a real SQL engine, through a thin dialect shim that answers
PostgreSQL's ``to_regclass`` from ``sqlite_master`` and swaps ``%s``
placeholders for ``?``. The PostgreSQL proofs live in
``tests/test_orrery/test_retrograde_embedding_pg.py``,
``tests/test_jobs_cli_pg.py`` and ``tests/test_api/test_scheduler_pg.py``.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterator, Literal

import pytest
from pydantic import ValidationError

from nexus import cli
from nexus.agents.memnon.utils.source_embeddings import (
    AUDITED_SOURCES,
    CHARACTER_EXPERIENCE_SOURCE,
    RETROGRADE_SUMMARY_SOURCE,
    count_stamped_without_vectors,
)
from nexus.agents.orrery.experience_embedding import (
    count_unembedded_rendered_experiences,
    drain_experience_embeddings_sync,
    unembedded_rendered_experience_ids,
)
from nexus.config import load_settings
from nexus.jobs.scheduler import SlotScheduler, experience_embedding_rounds
from tests.settings_helpers import settings_with

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

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()

    def __enter__(self) -> "_SqliteCursor":
        return self

    def __exit__(self, *_args: Any) -> Literal[False]:
        return False


class _SqliteConnection:
    """DBAPI connection over SQLite whose cursors speak PostgreSQL."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def __enter__(self) -> "_SqliteConnection":
        self._connection.__enter__()
        return self

    def __exit__(self, *exc: Any) -> Literal[False]:
        self._connection.__exit__(*exc)
        return False

    def cursor(self) -> _SqliteCursor:
        return _SqliteCursor(self._connection)


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


@pytest.fixture()
def experiences() -> Iterator[sqlite3.Connection]:
    """Three rendered rows owed vectors among every row the drain must skip."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE character_experiences (
            id INTEGER PRIMARY KEY,
            experience_text TEXT,
            invalidation_status TEXT NOT NULL,
            embedding_generated_at TEXT
        );
        INSERT INTO character_experiences VALUES
            (9, 'I remember the bell.', 'valid', NULL),
            (4, NULL, 'valid', NULL),
            (5, 'I remember the rain.', 'valid', NULL),
            (6, 'I remember a retracted day.', 'invalidated', NULL),
            (7, 'I remember the fire.', 'valid', '2196-01-01'),
            (3, 'I remember the flood.', 'valid', NULL);
        """
    )
    yield connection
    connection.close()


def test_drain_selects_oldest_rendered_valid_unstamped_experiences(
    experiences: sqlite3.Connection,
) -> None:
    """Unrendered, invalidated and already-stamped rows are never selected."""
    cursor = _SqliteCursor(experiences)
    assert unembedded_rendered_experience_ids(cursor, 2) == [3, 5]
    assert unembedded_rendered_experience_ids(cursor, 10) == [3, 5, 9]
    assert count_unembedded_rendered_experiences(cursor) == 3


def test_drain_selection_refuses_a_nonpositive_limit(
    experiences: sqlite3.Connection,
) -> None:
    """A zero limit is a caller bug, not an empty drain."""
    with pytest.raises(ValueError, match="must be positive, got 0"):
        unembedded_rendered_experience_ids(_SqliteCursor(experiences), 0)


def test_drain_without_owed_rows_never_reaches_the_embedder(
    experiences: sqlite3.Connection,
) -> None:
    """Nothing owed means no slot connection and no model load.

    The embedder would open a pooled PostgreSQL connection, which the default
    gate's connection guard fails loudly, so a clean zero proves the drain
    never called it.
    """
    experiences.execute(
        "UPDATE character_experiences SET embedding_generated_at = '2196-01-02' "
        "WHERE experience_text IS NOT NULL"
    )
    drained = drain_experience_embeddings_sync(
        _SqliteConnection(experiences),
        dbname="save_05",
        settings=load_settings(),
        limit=12,
    )
    assert drained == 0
    assert count_unembedded_rendered_experiences(_SqliteCursor(experiences)) == 0


def test_disabled_experiences_drain_nothing(
    experiences: sqlite3.Connection,
) -> None:
    """A disabled subsystem leaves owed rows alone, like its render lane."""
    settings = settings_with({"orrery.experiences.enabled": False})
    drained = drain_experience_embeddings_sync(
        _SqliteConnection(experiences), dbname="save_05", settings=settings, limit=12
    )
    assert drained == 0
    assert count_unembedded_rendered_experiences(_SqliteCursor(experiences)) == 3


def test_zero_embedding_limit_skips_the_lane_before_reading_its_settings() -> None:
    """An isolated pass never reads the lane's table, so it never embeds.

    The same absent Orrery section fails a default pass, so a clean zero
    proves the skipped lane stopped before reading it.
    """
    settings = load_settings().model_copy(update={"orrery": None})
    with pytest.raises(RuntimeError, match=r"\[orrery\]"):
        experience_embedding_rounds(settings, None)
    assert experience_embedding_rounds(settings, 0) == 0


def test_zero_configured_embedding_limit_is_invalid() -> None:
    """A typed configuration cannot disable the lane with an invalid bound."""
    with pytest.raises(ValidationError, match="max_embeddings_per_drain"):
        settings_with({"orrery.experiences.max_embeddings_per_drain": 0})


def test_embedding_limit_defaults_to_and_is_capped_by_the_configured_bound() -> None:
    """``None`` takes the configured bound; an explicit limit only lowers it."""
    settings = settings_with({"orrery.experiences.max_embeddings_per_drain": 5})
    assert experience_embedding_rounds(settings, None) == 5
    assert experience_embedding_rounds(settings, 2) == 2
    assert experience_embedding_rounds(settings, 9) == 5


def test_scheduler_pass_resolves_the_embedding_limit_before_connecting() -> None:
    """A negative limit fails before the pass opens a slot connection.

    The default gate fails any psycopg2 connection loudly, so this ValueError
    proves the pass reads ``experience_embedding_limit`` before any lane runs.
    """
    scheduler = SlotScheduler(5, dbname="save_05", settings=load_settings())
    with pytest.raises(ValueError, match="experience_embedding_limit must be non-"):
        scheduler._drain(experience_embedding_limit=-1)


def test_scheduler_pass_refuses_an_unknown_lane_limit() -> None:
    """A misspelled limit fails before ownership instead of isolating nothing."""
    scheduler = SlotScheduler(5, dbname="save_05", settings=load_settings())
    with pytest.raises(TypeError, match="experience_embeddings_limit"):
        scheduler.run_pass(experience_embeddings_limit=0)  # type: ignore[call-arg]


def _jobs_payload(
    stamped_without_vectors: dict[str, int], unembedded_experiences: int = 0
) -> dict[str, Any]:
    return {
        "scheduler": None,
        "queues": {},
        "non_terminal_jobs": [],
        "unembedded_accepted_chunks": 0,
        "unembedded_rendered_experiences": unembedded_experiences,
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


def test_jobs_output_names_owed_experience_vectors_only_when_present(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`nexus jobs` shows the rendered-experience backlog only while it exists."""
    clean = {"retrograde_summaries": 0, "character_experiences": 0}
    cli._print_jobs(_jobs_payload(clean))
    assert "unembedded_rendered_experiences" not in capsys.readouterr().out

    cli._print_jobs(_jobs_payload(clean, unembedded_experiences=3))
    assert capsys.readouterr().out.splitlines()[-1] == (
        "unembedded_rendered_experiences: 3"
    )


@pytest.mark.parametrize(
    "field", ["unembedded_rendered_experiences", "stamped_without_vectors"]
)
def test_jobs_output_refuses_a_pre_upgrade_payload(field: str) -> None:
    """A gateway older than the CLI is named, not papered over with a default."""
    payload = _jobs_payload({"retrograde_summaries": 0, "character_experiences": 0})
    del payload[field]
    with pytest.raises(RuntimeError, match=f"{field}.*restart"):
        cli._print_jobs(payload)
