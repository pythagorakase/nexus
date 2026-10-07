"""A data clone of a source behind the current stamp migrates before its pin.

Issue #1083: ``disposable_slot_database(..., include_data=True)`` wrote the
TEST story pin before it migrated the clone. The pin's UPDATE names
``global_variables.gaia_model`` (migration 117), so a source stamped below
117 could not be cloned with data. The reference corpus
``ref_codex_bakeoff_2026_07`` is stamped at 114 and is that source. The clone
reads it only through ``pg_dump``; nothing writes to it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing

import pytest
from psycopg2 import sql

from nexus.config import load_settings
from nexus.config.story_model import read_story_settings
from scripts import migrate
from tests.pg_fixtures import (
    SEAT_BACKFILL_JOB_TABLES,
    connect,
    disposable_slot_database,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.requires_corpus]

REFERENCE_CORPUS = "ref_codex_bakeoff_2026_07"


@pytest.fixture(scope="module")
def reference_corpus_clone() -> Iterator[str]:
    """Yield a disposable, migrated, TEST-pinned data clone of the corpus."""

    with disposable_slot_database(
        "qa640_1083_ref_corpus", source_db=REFERENCE_CORPUS, include_data=True
    ) as dbname:
        yield dbname


def test_reference_corpus_clones_with_data_and_pins_after_migrating(
    reference_corpus_clone: str,
) -> None:
    """The clone reaches the newest stamp, has the pin columns, and reads TEST."""

    newest = max(version for version, _, _ in migrate.discover_migrations())
    with closing(connect(reference_corpus_clone)) as conn, conn.cursor() as cur:
        cur.execute("SELECT max(version) FROM schema_migrations")
        assert cur.fetchone()[0] == newest
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'global_variables' "
            "AND column_name = 'gaia_model'"
        )
        assert cur.fetchone() is not None
        cur.execute("SELECT count(*) FROM narrative_chunks")
        assert cur.fetchone()[0] > 0
        # Migration 126 freezes active jobs' models from the pin present at
        # migration time, which for a data clone is the source's pin. This
        # corpus has no queued or leased jobs, so no row may carry a
        # migration_backfill resolution. The fixture itself refuses a clone
        # where one does (_refuse_source_pin_backfill); this records the
        # precondition, not the pin order.
        for table in SEAT_BACKFILL_JOB_TABLES:
            cur.execute(
                sql.SQL(
                    "SELECT count(*) FROM {} WHERE state IN ('queued', 'leased') "
                    "AND resolved_source = 'migration_backfill'"
                ).format(sql.Identifier(table))
            )
            assert cur.fetchone()[0] == 0, table

    story = read_story_settings(reference_corpus_clone)
    assert story.skald_model == "TEST"
    assert story.gaia_model is None
    test_models = {
        entry.id for entry in load_settings().global_.model.api_models["test"].models
    }
    assert story.skald_model in test_models
