"""Freeze deferred model identities and backfill active legacy work atomically."""

from typing import Any

from psycopg2 import sql

from nexus.config import load_settings
from nexus.config.story_model import StorySettings, resolve_seat

DDL = """
ALTER TABLE character_experience_jobs ADD COLUMN resolved_model text;
COMMENT ON COLUMN character_experience_jobs.resolved_model IS 'Literal registry model ID resolved in the accepting transaction; immutable across story repins. Active legacy jobs are backfilled during migration; terminal legacy rows stay NULL.';
ALTER TABLE character_experience_jobs ADD COLUMN resolved_source text;
COMMENT ON COLUMN character_experience_jobs.resolved_source IS 'Model selection source captured at enqueue (request, story_pin, story_follow, player_preference, seat_default, repository_default). migration_backfill identifies active pre-migration work; terminal legacy rows stay NULL.';

ALTER TABLE orrery_maturation_jobs ADD COLUMN resolved_model text;
COMMENT ON COLUMN orrery_maturation_jobs.resolved_model IS 'Literal registry model ID resolved in the accepting transaction; immutable across story repins. Active legacy jobs are backfilled during migration; terminal legacy rows stay NULL.';
ALTER TABLE orrery_maturation_jobs ADD COLUMN resolved_source text;
COMMENT ON COLUMN orrery_maturation_jobs.resolved_source IS 'Model selection source captured at enqueue (request, story_pin, story_follow, player_preference, seat_default, repository_default). migration_backfill identifies active pre-migration work; terminal legacy rows stay NULL.';

ALTER TABLE correspondence_compaction_jobs ADD COLUMN resolved_model text;
COMMENT ON COLUMN correspondence_compaction_jobs.resolved_model IS 'Literal registry model ID resolved in the accepting transaction; immutable across story repins. Active legacy jobs are backfilled during migration; terminal legacy rows stay NULL.';
ALTER TABLE correspondence_compaction_jobs ADD COLUMN resolved_source text;
COMMENT ON COLUMN correspondence_compaction_jobs.resolved_source IS 'Model selection source captured at enqueue (request, story_pin, story_follow, player_preference, seat_default, repository_default). migration_backfill identifies active pre-migration work; terminal legacy rows stay NULL.';

ALTER TABLE narrative_summary_jobs ADD COLUMN resolved_model text;
COMMENT ON COLUMN narrative_summary_jobs.resolved_model IS 'Literal registry model ID resolved in the accepting transaction; immutable across story repins. Active legacy jobs are backfilled during migration; terminal legacy rows stay NULL.';
ALTER TABLE narrative_summary_jobs ADD COLUMN resolved_source text;
COMMENT ON COLUMN narrative_summary_jobs.resolved_source IS 'Model selection source captured at enqueue (request, story_pin, story_follow, player_preference, seat_default, repository_default). migration_backfill identifies active pre-migration work; terminal legacy rows stay NULL.';

COMMENT ON COLUMN generation_attempt_manifests.story_pin IS 'Story model, Gaia model and context-window pins at dispatch, plus resolved_source from the captured seat resolution (NULL on historical attempts).';
"""

JOB_SEATS = {
    "character_experience_jobs": "orrery.experiences.model",
    "orrery_maturation_jobs": "orrery.retrograde.maturation.model_ref",
    "correspondence_compaction_jobs": "storyteller.correspondence.compaction_model",
    "narrative_summary_jobs": "summaries.model",
}


def run(conn: Any) -> None:
    """Resolve only active unresolved jobs, using this database's current pin."""
    settings = load_settings()
    with conn.cursor() as cur:
        cur.execute("SET LOCAL nexus.write_producer = 'migration'")
        cur.execute(DDL)
        cur.execute(
            "SELECT model, gaia_model, apex_context_window "
            "FROM global_variables WHERE id = TRUE FOR SHARE"
        )
        row = cur.fetchone()
        story = (
            StorySettings(
                skald_model=row[0],
                gaia_model=row[1],
                apex_context_window=row[2],
                dbname=conn.info.dbname,
            )
            if row
            else None
        )
        for table, seat in JOB_SEATS.items():
            unresolved = sql.SQL(
                "FROM {} WHERE state IN ('queued', 'leased') AND resolved_model IS NULL"
            ).format(sql.Identifier(table))
            cur.execute(sql.SQL("SELECT EXISTS (SELECT 1 {})").format(unresolved))
            if not cur.fetchone()[0]:
                continue
            if story is None:
                raise RuntimeError(
                    f"Cannot backfill {table}: story settings row is missing"
                )
            resolution = resolve_seat(seat, settings=settings, story=story)
            cur.execute(
                sql.SQL(
                    "UPDATE {} SET resolved_model=%s, resolved_source='migration_backfill' "
                    "WHERE state IN ('queued', 'leased') AND resolved_model IS NULL"
                ).format(sql.Identifier(table)),
                (resolution.model,),
            )
