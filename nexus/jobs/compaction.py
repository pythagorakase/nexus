"""Durable correspondence plans; retain journal-based retry and stale checks."""

from typing import Any
from uuid import uuid4

from psycopg2.extras import RealDictCursor

from nexus.database import is_connection_failure
from nexus.config.settings_models import DeferredWorkSettings
from nexus.config.story_model import persisted_job_model, resolve_enqueued_seat
from nexus.memory.correspondence import read_accepted_correspondence


def enqueue_compaction(cur: Any, *, accepting_chunk_id: int, floor_turns: int) -> None:
    """Enqueue in the accepting transaction once the retained floor is crossed."""
    if len(read_accepted_correspondence(cur).exchanges) > floor_turns:
        resolution = resolve_enqueued_seat(
            "storyteller.correspondence.compaction_model", cur
        )
        cur.execute(
            "INSERT INTO correspondence_compaction_jobs (accepting_chunk_id, resolved_model, resolved_source) "
            "VALUES (%s, %s, %s) ON CONFLICT (accepting_chunk_id) DO NOTHING",
            (accepting_chunk_id, resolution.model, resolution.source),
        )


def require_compaction_lease(cur: Any, *, job_id: int, owner: str, nonce: str) -> None:
    """Lock first, then evaluate the completion fence against the wall clock."""
    cur.execute(
        "SELECT id FROM correspondence_compaction_jobs WHERE id=%s FOR UPDATE",
        (job_id,),
    )
    cur.execute(
        """SELECT id FROM correspondence_compaction_jobs
        WHERE id=%s AND state='leased' AND locked_by=%s AND lease_nonce=%s
          AND lease_until > clock_timestamp()""",
        (job_id, owner, nonce),
    )
    if cur.fetchone() is None:
        raise RuntimeError(f"Compaction job {job_id} lost its lease")


def drain_compaction(conn: Any, *, cfg: DeferredWorkSettings, owner: str) -> int:
    """Run one nonce-fenced plan, replanning from the latest accepted exchange."""
    from nexus.api.commit_handler_sync import compact_accepted_correspondence_sync

    nonce = str(uuid4())
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, attempts, resolved_model, resolved_source FROM correspondence_compaction_jobs
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
        require_compaction_lease(cur, job_id=job["id"], owner=owner, nonce=nonce)

    from nexus.jobs.gate import report_leased_job, track_job_lease

    track_job_lease(
        "correspondence_compaction_jobs",
        job["id"],
        locked_by=owner,
        lease_nonce=nonce,
        duration=cfg.compaction_lease_duration_seconds,
    )
    report_leased_job("correspondence_compaction_jobs", job["id"])
    error = None
    try:
        model = persisted_job_model(job, table="correspondence_compaction_jobs")
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                context = read_accepted_correspondence(cur)
        if context.exchanges:
            compact_accepted_correspondence_sync(
                conn,
                accepting_chunk_id=context.exchanges[-1].chunk_id,
                completion_fence=fence,
                resolved_model=model,
            )
    except Exception as exc:
        if is_connection_failure(exc):
            raise
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
