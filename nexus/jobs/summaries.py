"""Scheduler-owned episode and season summary execution."""

from __future__ import annotations

from typing import Any

from psycopg2.extras import Json

from nexus.config import load_settings
from nexus.config.settings_models import NarrativeJobSettings
from nexus.database import database_url
from nexus.jobs.narrative_jobs import drain_job
from nexus.telemetry.usage import usage_context


def drain_summary(
    conn: Any, *, dbname: str, slot: int, cfg: NarrativeJobSettings, owner: str
) -> int:
    """Generate through the provider client and fence the reader-visible write."""

    def prepare(job: dict[str, Any]) -> dict[str, Any] | None:
        from scripts.summarize_narrative import DatabaseManager, SummaryGenerator

        db = DatabaseManager(db_url=database_url(dbname))
        try:
            episode = job["kind"] == "episode"
            exists = (
                db.episode_summary_exists(job["season"], job["episode"])
                if episode
                else db.season_summary_exists(job["season"])
            )
            if exists:
                return None
            if (
                episode
                and db.get_episode_chunk_span(job["season"], job["episode"]) is None
            ):
                raise RuntimeError(
                    f"Episode S{job['season']:02d}E{job['episode']:02d} has no chunks "
                    "to summarize"
                )
            settings = load_settings()
            if not settings.summaries.model:
                raise ValueError("No narrative summary model is configured")
            generator = SummaryGenerator(
                model=settings.summaries.model,
                db_manager=db,
                dry_run=True,
                prompt_on_conflict=False,
            )
            with usage_context(
                seat="summaries",
                slot=slot,
                run_id=(
                    str(job["generation_session_id"])
                    if job["generation_session_id"]
                    else None
                ),
            ):
                summary = (
                    generator.generate_episode_summary(job["season"], job["episode"])
                    if episode
                    else generator.generate_season_summary(job["season"])
                )
            if summary is None:
                raise RuntimeError(
                    generator.last_error or "Summary provider returned no summary"
                )
            return summary
        finally:
            db.engine.dispose()

    def complete(cur: Any, job: dict[str, Any], summary: dict[str, Any] | None) -> None:
        if summary is None:
            return
        if job["kind"] == "episode":
            cur.execute(
                "INSERT INTO seasons (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                (job["season"],),
            )
            cur.execute(
                """INSERT INTO episodes (season, episode, summary, chunk_span)
                SELECT %s, %s, %s, int8range(min(chunk_id), max(chunk_id)+1, '[)')
                FROM chunk_metadata WHERE season=%s AND episode=%s
                ON CONFLICT (season, episode) DO UPDATE
                SET summary=EXCLUDED.summary, chunk_span=EXCLUDED.chunk_span
                WHERE episodes.summary IS NULL""",
                (
                    job["season"],
                    job["episode"],
                    Json(summary),
                    job["season"],
                    job["episode"],
                ),
            )
        else:
            cur.execute(
                """INSERT INTO seasons (id, summary) VALUES (%s, %s)
                ON CONFLICT (id) DO UPDATE SET summary=EXCLUDED.summary
                WHERE seasons.summary IS NULL""",
                (job["season"], Json(summary)),
            )

    return drain_job(
        conn,
        table="narrative_summary_jobs",
        owner=owner,
        cfg=cfg,
        prepare=prepare,
        complete=complete,
    )
