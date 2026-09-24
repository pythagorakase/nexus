"""One read-only status source for CLI, gateway and QA deferred-work queues."""

from __future__ import annotations

import json
from typing import Any

from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.experiences import load_experience_status_sync
from nexus.agents.orrery.retrograde_maturation import (
    _connect_for_slot,
    load_maturation_status_sync,
)

_SHARED_STATES = ("queued", "leased", "succeeded", "failed", "stale_rejected")


def _queue_status(cur: Any, table: str, queue: str) -> dict[str, Any]:
    cur.execute(
        sql.SQL(
            """
            SELECT jsonb_build_object(
                'queued', count(*) FILTER (WHERE state='queued'),
                'leased', count(*) FILTER (WHERE state='leased'),
                'succeeded', count(*) FILTER (WHERE state='succeeded'),
                'failed', count(*) FILTER (WHERE state='failed'),
                'stale_rejected', count(*) FILTER (WHERE state='stale_rejected')
            ) AS counts,
            coalesce(jsonb_agg(jsonb_build_object(
                'id', id, 'queue', %s, 'state', state::text, 'attempts', attempts,
                'generation_session_id', generation_session_id,
                'available_at', available_at, 'lease_until', lease_until,
                'last_error', last_error
            ) ORDER BY id) FILTER (WHERE state IN ('queued','leased')), '[]'::jsonb)
                AS non_terminal_jobs
            FROM {}
        """
        ).format(sql.Identifier(table)),
        (queue,),
    )
    return dict(cur.fetchone())


def load_job_queues_sync(conn: Any) -> dict[str, Any]:
    """Read each queue atomically so its counts and job list always agree."""
    from nexus.agents.orrery.retrograde_markers import RETROGRADE_PROLOGUE_MARKER

    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        queues = {
            "narration": _queue_status(cur, "orrery_narration_jobs", "narration"),
            "experience_render": load_experience_status_sync(cur),
            "retrograde_maturation": load_maturation_status_sync(cur),
            "correspondence_compaction": _queue_status(
                cur, "correspondence_compaction_jobs", "correspondence_compaction"
            ),
        }
        cur.execute(
            "SELECT version_id, generation_session_id::text FROM relationship_milestone_queue WHERE event_id IS NULL ORDER BY version_id"
        )
        pending = [dict(row) for row in cur.fetchall()]
        queues["relationship_milestone"] = {
            "counts": {"pending": len(pending)},
            "non_terminal_jobs": [
                {
                    "id": row["version_id"],
                    "generation_session_id": row["generation_session_id"],
                    "state": "pending",
                    "queue": "relationship_milestone",
                }
                for row in pending
            ],
        }
        cur.execute(
            """
            SELECT owner_id, lease_nonce::text, heartbeat_at::text, expires_at::text,
                   expires_at > clock_timestamp() AS active, current_job, last_error,
                   CASE WHEN expires_at > clock_timestamp() THEN 'owner'
                        ELSE 'observer' END AS state
            FROM deferred_work_scheduler WHERE id
            """
        )
        scheduler = cur.fetchone()
        cur.execute(
            """
            SELECT count(*) AS count FROM narrative_chunks n
            JOIN chunk_metadata m ON m.chunk_id = n.id
            WHERE n.embedding_generated_at IS NULL AND m.world_layer = 'primary'
              AND NOT (coalesce(n.authorial_directives, '[]'::jsonb) @> %s::jsonb)
            """,
            (json.dumps([RETROGRADE_PROLOGUE_MARKER]),),
        )
        unembedded = int(cur.fetchone()["count"])
    counts = {
        state: sum(int(queue["counts"].get(state, 0)) for queue in queues.values())
        for state in (*_SHARED_STATES, "pending")
    }
    jobs = sorted(
        (job for queue in queues.values() for job in queue["non_terminal_jobs"]),
        key=lambda job: (str(job["queue"]), int(job["id"])),
    )
    return {
        "queues": queues,
        "counts": counts,
        "non_terminal_jobs": jobs,
        "scheduler": dict(scheduler) if scheduler else None,
        "unembedded_accepted_chunks": unembedded,
    }


def load_job_queues_for_slot_sync(slot: int) -> dict[str, Any]:
    """Return the same complete status payload used by runtime/status."""
    conn = _connect_for_slot(slot)
    try:
        return load_job_queues_sync(conn)
    finally:
        conn.close()
