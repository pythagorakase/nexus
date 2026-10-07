"""A data clone of a source behind the current stamp migrates before its pin.

Issue #1083: ``disposable_slot_database(..., include_data=True)`` wrote the
TEST story pin before it migrated the clone. The pin's UPDATE names
``global_variables.gaia_model`` (migration 117), so a source stamped below
117 could not be cloned with data. The reference corpus
``ref_codex_bakeoff_2026_07`` is stamped at 114 and is that source. Every
test here reads it only through ``pg_dump``; nothing writes to it. Edits are
applied to a disposable copy restored from that dump.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import closing, contextmanager

import pytest

from nexus.config import load_settings
from nexus.config.story_model import StorySettings, read_story_settings, resolve_seat
from nexus.database import subprocess_env
from scripts import migrate
from tests.pg_fixtures import (
    connect,
    disposable_database,
    disposable_slot_database,
    seat_backfill_job_seats,
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


@contextmanager
def edited_corpus_source(prefix: str, statement: str) -> Iterator[str]:
    """Yield a disposable copy of the reference corpus with one row edited.

    The corpus is read only through ``pg_dump``; ``statement`` runs against
    the disposable copy and must touch exactly one row.
    """

    with disposable_database(prefix) as source:
        with tempfile.TemporaryDirectory(prefix="nexus-1083-") as archive_dir:
            archive_path = os.path.join(archive_dir, "corpus.dump")
            subprocess.run(
                [
                    "pg_dump",
                    "--format=custom",
                    "--file",
                    archive_path,
                    "--dbname",
                    REFERENCE_CORPUS,
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
                    source,
                    archive_path,
                ],
                check=True,
                capture_output=True,
                text=True,
                env=subprocess_env(),
            )
        with closing(connect(source)) as conn, conn, conn.cursor() as cur:
            cur.execute(statement)
            assert cur.rowcount == 1
        yield source


def seat_models(source: str, seat: str) -> tuple[str, str]:
    """Return ``seat``'s model under ``source``'s story pin and under TEST."""

    with closing(connect(source)) as conn, conn.cursor() as cur:
        cur.execute("SELECT model FROM global_variables WHERE id = TRUE")
        source_pin = cur.fetchone()[0]
    settings = load_settings()
    return (
        resolve_seat(
            seat,
            settings=settings,
            story=StorySettings(skald_model=source_pin, gaia_model=None),
        ).model,
        resolve_seat(
            seat,
            settings=settings,
            story=StorySettings(skald_model="TEST", gaia_model=None),
        ).model,
    )


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

    story = read_story_settings(reference_corpus_clone)
    assert story.skald_model == "TEST"
    assert story.gaia_model is None
    test_models = {
        entry.id for entry in load_settings().global_.model.api_models["test"].models
    }
    assert story.skald_model in test_models


def test_clone_refuses_a_follow_story_job_frozen_under_the_source_pin() -> None:
    """Migration 126 freezes a queued follow_story job to the source's model.

    The source's pin and TEST resolve the experience seat to different
    models, so the TEST pin written after migrating cannot reach the frozen
    row, and the fixture refuses the clone instead of yielding it.
    """

    table = "character_experience_jobs"
    with edited_corpus_source(
        "qa640_1083_src",
        f"INSERT INTO {table} (boundary_chunk_id, scene_end_chunk_id, "
        "world_layer, boundary_season, boundary_episode, boundary_scene, "
        "scene_end_season, scene_end_episode, scene_end_scene, batch_ordinal, "
        "experience_ids, slot, state, requested_model, source_digest) "
        "SELECT min(id), min(id), 'primary', 1, 1, 1, 1, 1, 1, 0, "
        "ARRAY[1]::bigint[], 'qa640_1083', 'queued', "
        "(SELECT model FROM global_variables WHERE id = TRUE), 'qa640_1083' "
        "FROM narrative_chunks",
    ) as source:
        source_model, test_model = seat_models(source, seat_backfill_job_seats()[table])
        assert source_model != test_model
        with pytest.raises(
            RuntimeError, match=f"migration 126 froze 1 active {table} rows"
        ):
            with disposable_slot_database(
                "qa640_1083_guard", source_db=source, include_data=True
            ):
                pass


def test_clone_admits_a_fixed_seat_job_frozen_under_the_source_pin() -> None:
    """A queued job on a fixed seat resolves to the seat default under any pin.

    Migration 126 freezes it under the source's pin to the same model the
    TEST pin would give, so the clone yields with the row intact and the
    story pin reading TEST.
    """

    table = "orrery_maturation_jobs"
    with edited_corpus_source(
        "qa640_1083_src",
        f"UPDATE {table} SET state = 'queued' "
        f"WHERE id = (SELECT min(id) FROM {table})",
    ) as source:
        source_model, test_model = seat_models(source, seat_backfill_job_seats()[table])
        assert source_model == test_model
        with disposable_slot_database(
            "qa640_1083_fixed", source_db=source, include_data=True
        ) as clone:
            with closing(connect(clone)) as conn, conn.cursor() as cur:
                cur.execute(
                    f"SELECT resolved_model FROM {table} "
                    "WHERE state = 'queued' AND resolved_source = 'migration_backfill'"
                )
                assert cur.fetchall() == [(test_model,)]
            assert read_story_settings(clone).skald_model == "TEST"
