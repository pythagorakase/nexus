"""Lease and completion fences shared by narrative embeddings and summaries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from nexus.config.settings_models import NarrativeJobSettings
from nexus.jobs.gate import report_leased_job, track_job_lease


def require_lease(cur: Any, table: str, job: dict[str, Any]) -> None:
    """Lock the row before checking the nonce and the current wall clock."""
    cur.execute(
        sql.SQL("SELECT id FROM {} WHERE id=%s FOR UPDATE").format(
            sql.Identifier(table)
        ),
        (job["id"],),
    )
    cur.execute(
        sql.SQL(
            """SELECT id FROM {} WHERE id=%s AND state='leased'
            AND locked_by=%s AND lease_nonce=%s
            AND lease_until > clock_timestamp()"""
        ).format(sql.Identifier(table)),
        (job["id"], job["locked_by"], job["lease_nonce"]),
    )
    if cur.fetchone() is None:
        raise RuntimeError(f"{table}:{job['id']} lost its execution lease")


def drain_job(
    conn: Any,
    *,
    table: str,
    owner: str,
    cfg: NarrativeJobSettings,
    prepare: Callable[[dict[str, Any]], Any],
    complete: Callable[[Any, dict[str, Any], Any], None],
) -> int:
    """Prepare outside SQL, then atomically commit domain output and completion."""
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            sql.SQL(
                """SELECT * FROM {} WHERE
                (state='queued' AND available_at <= clock_timestamp()) OR
                (state='leased' AND lease_until <= clock_timestamp())
                ORDER BY available_at, id LIMIT 1 FOR UPDATE SKIP LOCKED"""
            ).format(sql.Identifier(table))
        )
        job = cur.fetchone()
        if job is None:
            return 0
        if job["attempts"] >= cfg.max_attempts:
            cur.execute(
                sql.SQL(
                    """UPDATE {} SET state='failed', error_class='AttemptsExhausted',
                    last_error='Execution attempts exhausted during recovery',
                    lease_until=NULL, locked_by=NULL, lease_nonce=NULL, updated_at=now()
                    WHERE id=%s"""
                ).format(sql.Identifier(table)),
                (job["id"],),
            )
            return 1
        job.update(locked_by=owner, lease_nonce=str(uuid4()))
        cur.execute(
            sql.SQL(
                """UPDATE {} SET state='leased', attempts=attempts+1,
                locked_by=%s, lease_nonce=%s,
                lease_until=clock_timestamp()+(%s * interval '1 second'), updated_at=now()
                WHERE id=%s"""
            ).format(sql.Identifier(table)),
            (owner, job["lease_nonce"], cfg.lease_duration_seconds, job["id"]),
        )
    track_job_lease(
        table,
        job["id"],
        locked_by=owner,
        lease_nonce=job["lease_nonce"],
        duration=cfg.lease_duration_seconds,
    )
    report_leased_job(table, job["id"])
    try:
        result = prepare(job)
        with conn, conn.cursor() as cur:
            require_lease(cur, table, job)
            complete(cur, job, result)
            cur.execute(
                sql.SQL(
                    """UPDATE {} SET state='succeeded', last_error=NULL,
                    error_class=NULL, lease_until=NULL, locked_by=NULL,
                    lease_nonce=NULL, updated_at=now() WHERE id=%s"""
                ).format(sql.Identifier(table)),
                (job["id"],),
            )
    except Exception as exc:
        with conn, conn.cursor() as cur:
            require_lease(cur, table, job)
            cur.execute(
                sql.SQL(
                    """UPDATE {} SET state=%s::orrery_job_state,
                    last_error=%s, error_class=%s,
                    available_at=clock_timestamp()+(%s * interval '1 second'),
                    lease_until=NULL, locked_by=NULL, lease_nonce=NULL, updated_at=now()
                    WHERE id=%s"""
                ).format(sql.Identifier(table)),
                (
                    "failed" if job["attempts"] + 1 >= cfg.max_attempts else "queued",
                    str(exc),
                    type(exc).__name__,
                    cfg.retry_delay_seconds,
                    job["id"],
                ),
            )
        raise
    return 1
