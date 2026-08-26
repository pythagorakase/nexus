"""Unified public status for provider-capable durable Orrery queues."""

from __future__ import annotations

from typing import Any

from psycopg2.extras import RealDictCursor

from nexus.agents.orrery.experiences import load_experience_status_sync
from nexus.agents.orrery.retrograde_maturation import (
    _connect_for_slot,
    load_maturation_status_sync,
)


_SHARED_STATES = ("queued", "leased", "succeeded", "failed")


def load_job_queues_for_slot_sync(slot: int) -> dict[str, Any]:
    """Return every provider-capable durable queue for one save slot."""

    conn = _connect_for_slot(slot)
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                queues = {
                    "retrograde_maturation": load_maturation_status_sync(cur),
                    "experience_render": load_experience_status_sync(cur),
                }
    finally:
        conn.close()

    counts = {
        state: sum(int(queue["counts"][state]) for queue in queues.values())
        for state in _SHARED_STATES
    }
    non_terminal_jobs = sorted(
        (job for queue in queues.values() for job in queue["non_terminal_jobs"]),
        key=lambda job: (str(job["queue"]), int(job["id"])),
    )
    return {
        "queues": queues,
        "counts": counts,
        "non_terminal_jobs": non_terminal_jobs,
    }
