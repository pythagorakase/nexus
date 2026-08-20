#!/usr/bin/env python3
"""Benchmark the experience enqueue fence in a disposable PostgreSQL clone."""

from __future__ import annotations

import os
from pathlib import Path
from statistics import median
from typing import Any
from uuid import uuid4

import psycopg2
from psycopg2 import sql

from nexus.agents.orrery.experiences import _ENQUEUE_CANDIDATES_SQL
from scripts import new_story_setup


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "migrations" / "111_experience_job_enqueue_gin_fence.sql"
INDEX_NAME = "ix_character_experience_jobs_pending_experience_ids"
OLD_MEMBERSHIP = "experience.id = ANY(prior_job.experience_ids)"
NEW_MEMBERSHIP = "prior_job.experience_ids @> ARRAY[experience.id]::bigint[]"


def _connect(dbname: str) -> Any:
    """Open a direct PostgreSQL connection."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


def _index_names(node: dict[str, Any]) -> set[str]:
    names = {str(node["Index Name"])} if "Index Name" in node else set()
    for child in node.get("Plans", []):
        names.update(_index_names(child))
    return names


def _explain_samples(
    cur: Any,
    query: str,
    params: tuple[Any, ...],
) -> tuple[list[float], dict[str, Any]]:
    statement = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query
    cur.execute(statement, params)
    cur.fetchone()
    samples: list[float] = []
    explanation: dict[str, Any] = {}
    for _sample in range(5):
        cur.execute(statement, params)
        explanation = cur.fetchone()[0][0]
        samples.append(float(explanation["Execution Time"]))
    return samples, explanation


def _plant_shape(cur: Any) -> int:
    cur.execute(
        "INSERT INTO narrative_chunks (raw_text) VALUES ('benchmark scene end') "
        "RETURNING id"
    )
    scene_end_chunk_id = int(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO narrative_chunks (raw_text) VALUES ('benchmark boundary') "
        "RETURNING id"
    )
    boundary_chunk_id = int(cur.fetchone()[0])
    cur.execute(
        """
        WITH owners AS (
            INSERT INTO entities (kind)
            SELECT 'character'
            FROM generate_series(1, 5000)
            RETURNING id
        )
        INSERT INTO character_experiences (
            character_entity_id, anchor_chunk_id, world_event_ids,
            basis, seed_summary, salience, source_digest, world_layer
        )
        SELECT id, %s, ARRAY[id], 'participant',
               'Benchmark fence seed ' || id::text, 0.5,
               'qa-wt720-benchmark-' || id::text, 'primary'
        FROM owners
        """,
        (scene_end_chunk_id,),
    )
    cur.execute(
        """
        INSERT INTO character_experience_jobs (
            boundary_chunk_id, scene_end_chunk_id, world_layer,
            boundary_season, boundary_episode, boundary_scene,
            scene_end_season, scene_end_episode, scene_end_scene,
            batch_ordinal, experience_ids, slot, state, requested_model,
            source_digest
        )
        SELECT %s, %s, 'primary', 1, 1, 2, 1, 1, 1,
               grouped.batch_ordinal, grouped.experience_ids,
               'qa_wt720', 'queued', '@openai.gaia',
               'qa-wt720-benchmark-job-' || grouped.batch_ordinal::text
        FROM (
            SELECT ((numbered.ordinal - 1) / 10)::integer AS batch_ordinal,
                   array_agg(numbered.id ORDER BY numbered.id) AS experience_ids
            FROM (
                SELECT id, row_number() OVER (ORDER BY id) AS ordinal
                FROM character_experiences
                WHERE source_digest LIKE 'qa-wt720-benchmark-%%'
            ) numbered
            GROUP BY ((numbered.ordinal - 1) / 10)::integer
        ) grouped
        """,
        (boundary_chunk_id, scene_end_chunk_id),
    )
    cur.execute("ANALYZE character_experiences")
    cur.execute("ANALYZE character_experience_jobs")
    return scene_end_chunk_id


def _print_result(
    label: str,
    samples: list[float],
    explanation: dict[str, Any],
) -> None:
    plan = explanation["Plan"]
    print(f"{label}_execution_ms={','.join(f'{value:.3f}' for value in samples)}")
    print(f"{label}_median_ms={median(samples):.3f}")
    print(
        f"{label}_buffers="
        f"shared_hit:{int(plan.get('Shared Hit Blocks', 0))},"
        f"shared_read:{int(plan.get('Shared Read Blocks', 0))},"
        f"temp_read:{int(plan.get('Temp Read Blocks', 0))},"
        f"temp_written:{int(plan.get('Temp Written Blocks', 0))}"
    )
    print(f"{label}_indexes={','.join(sorted(_index_names(plan))) or '<none>'}")


def main() -> None:
    """Run the fixed 5k/500/10 benchmark and print five-sample medians."""

    dbname = f"qa_wt720_benchmark_{uuid4().hex[:8]}"
    admin: Any = None
    original_use_pool = new_story_setup.USE_POOL
    try:
        admin = _connect("postgres")
        admin.autocommit = True
        new_story_setup.USE_POOL = False
        new_story_setup.initialize_slot_database(
            dbname,
            source_db="NEXUS_template",
        )
        with _connect(dbname) as conn:
            with conn.cursor() as cur:
                scene_end_chunk_id = _plant_shape(cur)
                params = (scene_end_chunk_id, "primary", None, None)
                old_query = _ENQUEUE_CANDIDATES_SQL.replace(
                    NEW_MEMBERSHIP, OLD_MEMBERSHIP
                )
                if old_query == _ENQUEUE_CANDIDATES_SQL:
                    raise RuntimeError(
                        "Production enqueue membership predicate changed"
                    )
                cur.execute(sql.SQL("DROP INDEX {}").format(sql.Identifier(INDEX_NAME)))
                before_samples, before_explanation = _explain_samples(
                    cur, old_query, params
                )
                cur.execute(MIGRATION.read_text())
                cur.execute("ANALYZE character_experience_jobs")
                after_samples, after_explanation = _explain_samples(
                    cur, _ENQUEUE_CANDIDATES_SQL, params
                )
                after_indexes = _index_names(after_explanation["Plan"])
                if INDEX_NAME not in after_indexes:
                    raise RuntimeError(f"Planner did not use {INDEX_NAME}")
                before_median = median(before_samples)
                after_median = median(after_samples)
                speedup = before_median / after_median
                _print_result("before", before_samples, before_explanation)
                _print_result("after", after_samples, after_explanation)
                print(f"median_speedup={speedup:.2f}x")
                if speedup < 10.0:
                    raise RuntimeError(
                        f"Median speedup {speedup:.2f}x is below the 10x target"
                    )
    finally:
        new_story_setup.USE_POOL = original_use_pool
        if admin is not None:
            with admin.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (dbname,),
                )
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                )
            admin.close()


if __name__ == "__main__":
    main()
