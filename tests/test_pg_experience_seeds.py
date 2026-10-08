"""The shared experience seeds enqueue through the production experience path."""

from __future__ import annotations

from contextlib import closing

import pytest

from nexus.config import load_settings_as_dict
from tests.pg_fixtures import (
    connect,
    disposable_slot_database,
    seed_experience_candidates,
    seed_experience_render_job,
    seed_protagonist,
)

pytestmark = pytest.mark.requires_postgres


def test_seed_experience_render_job_enqueues_one_job() -> None:
    """One queued job holds the two seeds anchored at the scene chunk."""

    settings = load_settings_as_dict()
    with disposable_slot_database("qa640_816_experience_seed") as dbname:
        seed_protagonist(dbname)
        seed = seed_experience_render_job(
            dbname, settings=settings, label="Seed Proof", slot=736
        )
        with closing(connect(dbname)) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, state::text, experience_ids "
                "FROM character_experience_jobs"
            )
            jobs = cur.fetchall()
            assert jobs == [(seed.job_id, "queued", seed.experience_ids)]
            cur.execute(
                "SELECT id, anchor_chunk_id FROM character_experiences ORDER BY id"
            )
            experiences = cur.fetchall()
            assert [row[0] for row in experiences] == sorted(seed.experience_ids)
            assert len(experiences) == 2
            assert {row[1] for row in experiences} == {seed.scene_end_chunk_id}
            cur.execute(
                "SELECT cm.world_time = gv.base_timestamp "
                "FROM chunk_metadata cm, global_variables gv "
                "WHERE gv.id = true AND cm.chunk_id = %s",
                (seed.scene_end_chunk_id,),
            )
            assert cur.fetchone() == (True,)


def test_seed_experience_candidates_needs_a_clock() -> None:
    """Without a story clock the seed fails by name before inserting."""

    with disposable_slot_database("qa640_816_experience_seed") as dbname:
        with pytest.raises(AssertionError, match="seed_experience_candidates"):
            seed_experience_candidates(
                dbname, settings=load_settings_as_dict(), label="No Clock"
            )
