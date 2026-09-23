"""Durable correspondence plans; retain journal-based retry and stale checks."""

from typing import Any
from uuid import uuid4

from psycopg2.extras import RealDictCursor

from nexus.config.settings_models import DeferredWorkSettings
from nexus.memory.correspondence import read_accepted_correspondence


def enqueue_compaction(cur: Any, *, accepting_chunk_id: int, floor_turns: int) -> None:
    """Enqueue in the accepting transaction once the retained floor is crossed."""
    if len(read_accepted_correspondence(cur).exchanges) > floor_turns:
        cur.execute(
            "INSERT INTO correspondence_compaction_jobs (accepting_chunk_id) "
            "VALUES (%s) ON CONFLICT (accepting_chunk_id) DO NOTHING",
            (accepting_chunk_id,),
        )


def drain_compaction(conn: Any, *, cfg: DeferredWorkSettings, owner: str) -> int:
    """Run one nonce-fenced plan, replanning from the latest accepted exchange."""
    from nexus.api.commit_handler_sync import compact_accepted_correspondence_sync

    nonce = str(uuid4())
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, attempts FROM correspondence_compaction_jobs
                WHERE (state = 'queued' AND available_at <= clock_timestamp())
                   OR (state = 'leased' AND lease_until < clock_timestamp())
                ORDER BY available_at, id LIMIT 1 FOR UPDATE SKIP LOCKED
                """
            )
            job = cur.fetchone()
            if job is None:
                return 0
            cur.execute(
                """
                UPDATE correspondence_compaction_jobs SET state = 'leased',
                    locked_by = %s, lease_nonce = %s,
                    lease_until = clock_timestamp() + (%s * interval '1 second'),
                    attempts = attempts + 1, updated_at = now()
                WHERE id = %s
                """,
                (owner, nonce, cfg.compaction_lease_duration_seconds, job["id"]),
            )

    def fence(cur: Any) -> None:
        cur.execute(
            """
            SELECT id FROM correspondence_compaction_jobs
            WHERE id = %s AND state = 'leased' AND locked_by = %s
              AND lease_nonce = %s AND lease_until > clock_timestamp()
            FOR UPDATE
            """,
            (job["id"], owner, nonce),
        )
        if cur.fetchone() is None:
            raise RuntimeError(f"Compaction job {job['id']} lost its lease")

    from nexus.jobs.gate import report_leased_job

    report_leased_job("correspondence_compaction_jobs", job["id"])
    error = None
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                context = read_accepted_correspondence(cur)
        if context.exchanges:
            compact_accepted_correspondence_sync(
                conn,
                accepting_chunk_id=context.exchanges[-1].chunk_id,
                completion_fence=fence,
            )
    except Exception as exc:
        error = str(exc)
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            fence(cur)
            state = (
                "succeeded"
                if error is None
                else (
                    "queued"
                    if job["attempts"] + 1 < cfg.compaction_max_attempts
                    else "failed"
                )
            )
            cur.execute(
                """
                UPDATE correspondence_compaction_jobs
                SET state = %s::orrery_job_state, last_error = %s,
                    available_at = clock_timestamp() + (%s * interval '1 second'),
                    lease_until = NULL, locked_by = NULL, lease_nonce = NULL,
                    updated_at = now()
                WHERE id = %s
                """,
                (state, error, cfg.compaction_retry_delay_seconds, job["id"]),
            )
    if error:
        raise RuntimeError(f"Compaction job {job['id']}: {error}")
    return 1
