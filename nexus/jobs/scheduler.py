"""One durable, preemptible recovery owner for each slot database."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import psycopg2
from psycopg2.extras import RealDictCursor

from nexus.config import load_settings_as_dict
from nexus.config.settings_models import DeferredWorkSettings
from nexus.database import connection_kwargs
from nexus.jobs.gate import SchedulerStopped, provider_gate

logger = logging.getLogger(__name__)


class SlotScheduler:
    """Own one slot's lease and drain existing domain queues on an idle clock."""

    def __init__(
        self,
        slot: int,
        *,
        dbname: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        from nexus.api.slot_utils import require_slot_dbname

        self.slot = slot
        self.dbname = dbname or require_slot_dbname(slot=slot)
        self.settings = settings or load_settings_as_dict()
        self.cfg = DeferredWorkSettings.model_validate(
            self.settings["runtime"]["scheduler"]
        )
        self.owner = f"gateway:{os.getpid()}:{uuid4()}"
        self.nonce = str(uuid4())
        self.stopping = threading.Event()
        self.wakeup = threading.Event()
        self._thread: threading.Thread | None = None
        self._heartbeat: threading.Thread | None = None
        self._heartbeat_stop = threading.Event()

    def connect(self) -> Any:
        """Open an independent connection to this scheduler's explicit database."""
        return psycopg2.connect(**connection_kwargs(self.dbname))

    def acquire(self) -> bool:
        """Acquire only a vacant or expired singleton; never steal a live owner."""
        conn = self.connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO deferred_work_scheduler
                        (id, owner_id, lease_nonce, heartbeat_at, expires_at)
                    VALUES (true, %s, %s, clock_timestamp(),
                        clock_timestamp() + (%s * interval '1 second'))
                    ON CONFLICT (id) DO UPDATE SET
                        owner_id = EXCLUDED.owner_id, lease_nonce = EXCLUDED.lease_nonce,
                        heartbeat_at = EXCLUDED.heartbeat_at, expires_at = EXCLUDED.expires_at,
                        current_job = NULL, last_error = NULL
                    WHERE deferred_work_scheduler.expires_at <= clock_timestamp()
                    RETURNING id
                    """,
                    (self.owner, self.nonce, self.cfg.lease_duration_seconds),
                )
                return cur.fetchone() is not None
        finally:
            conn.close()

    def renew(self) -> bool:
        """Renew only this unexpired acquisition."""
        conn = self.connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE deferred_work_scheduler
                    SET heartbeat_at = clock_timestamp(),
                        expires_at = clock_timestamp() + (%s * interval '1 second')
                    WHERE id AND owner_id = %s AND lease_nonce = %s
                      AND expires_at > clock_timestamp()
                    """,
                    (self.cfg.lease_duration_seconds, self.owner, self.nonce),
                )
                return cur.rowcount == 1
        finally:
            conn.close()

    def release(self) -> None:
        """Expire our acquisition without erasing its diagnostic heartbeat."""
        conn = self.connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE deferred_work_scheduler
                    SET expires_at = clock_timestamp(), current_job = NULL
                    WHERE id AND owner_id = %s AND lease_nonce = %s
                    """,
                    (self.owner, self.nonce),
                )
        finally:
            conn.close()

    def checkpoint(self) -> None:
        """Wait for generation; stop before new work if ownership is lost."""
        while not self.stopping.is_set():
            conn = self.connect()
            try:
                with conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM deferred_work_scheduler
                            WHERE id AND owner_id = %s AND lease_nonce = %s
                              AND expires_at > clock_timestamp()
                        ), EXISTS (
                            SELECT 1 FROM narrative_generation_lease
                            WHERE id AND expires_at > clock_timestamp()
                        )
                        """,
                        (self.owner, self.nonce),
                    )
                    owned, generating = cur.fetchone()
            finally:
                conn.close()
            if not owned:
                raise SchedulerStopped("Scheduler ownership expired or changed")
            if not generating:
                return
            self.stopping.wait(self.cfg.generation_wait_seconds)
        raise SchedulerStopped("Scheduler is stopping")

    def _report(self, job: str | None, error: str | None = None) -> None:
        conn = self.connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE deferred_work_scheduler SET current_job = %s, last_error = %s
                    WHERE id AND owner_id = %s AND lease_nonce = %s
                      AND expires_at > clock_timestamp()
                    """,
                    (job, error, self.owner, self.nonce),
                )
        finally:
            conn.close()

    def _heartbeats(self) -> None:
        try:
            while not self._heartbeat_stop.wait(self.cfg.heartbeat_interval_seconds):
                if not self.renew():
                    self.stopping.set()
                    self.wakeup.set()
                    return
        except Exception:
            logger.exception("Scheduler heartbeat failed for %s", self.dbname)
            self.stopping.set()
            self.wakeup.set()

    def _start_heartbeat(self) -> None:
        self._heartbeat_stop.clear()
        self._heartbeat = threading.Thread(
            target=self._heartbeats,
            name=f"scheduler-heartbeat-{self.dbname}",
            daemon=True,
        )
        self._heartbeat.start()

    def _end_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat:
            self._heartbeat.join(
                timeout=self.settings["runtime"]["health"]["stop_grace_seconds"]
            )

    def run_pass(self, **limits: Any) -> dict[str, Any]:
        """Run one operator pass under the very same ownership and heartbeat."""
        if not self.acquire():
            return {"owner": False, "drained": False}
        self._start_heartbeat()
        try:
            return self._drain(**limits)
        finally:
            self._end_heartbeat()
            self.release()

    def _drain(self, **limits: Any) -> dict[str, Any]:
        from nexus.agents.orrery import worker
        from nexus.agents.orrery.retrograde_maturation import drain_maturation_jobs_sync
        from nexus.jobs.compaction import drain_compaction

        result: dict[str, Any] = {"owner": True, "drained": True}
        conn = self.connect()
        try:
            with provider_gate(self.checkpoint, self._report):
                self.checkpoint()
                self._report("promotion")
                result["promotion"] = worker.promote_pending_resolutions_sync(
                    self.slot,
                    settings=self.settings,
                    conn=conn,
                    limit=limits.get("promotion_limit") or self.cfg.promotion_limit,
                )
                queues: list[tuple[str, int, Callable[[], Any]]] = [
                    (
                        "orrery_narration_jobs",
                        self.settings["orrery"]["narration"]["max_jobs_per_drain"],
                        lambda: worker.drain_narration_outbox_sync(
                            self.slot, conn=conn, settings=self.settings, limit=1
                        ),
                    ),
                    (
                        "character_experience_jobs",
                        self.settings["orrery"]["experiences"]["max_jobs_per_drain"],
                        lambda: worker.drain_experience_outbox_sync(
                            self.slot, conn=conn, settings=self.settings, limit=1
                        ),
                    ),
                    (
                        "orrery_maturation_jobs",
                        self.settings["orrery"]["retrograde"]["maturation"][
                            "max_jobs_per_drain"
                        ],
                        lambda: drain_maturation_jobs_sync(
                            self.slot, conn=conn, settings=self.settings, limit=1
                        ),
                    ),
                ]
                for (name, maximum, drain), limit_name in zip(
                    queues, ("narration_limit", "experience_limit", "maturation_limit")
                ):
                    requested = limits.get(limit_name)
                    if requested is not None:
                        if requested < 0:
                            raise ValueError(f"{limit_name} must be non-negative")
                        maximum = min(maximum, requested)
                    totals = [0, 0]
                    for _ in range(maximum):
                        self.checkpoint()
                        self._report(name)
                        counts = drain()
                        totals = [a + b for a, b in zip(totals, counts)]
                        if counts == (0, 0):
                            break
                    result[name] = totals
                self.checkpoint()
                self._report("relationship_milestone_queue")
                result["relationship_milestone_queue"] = self._recover_milestones(conn)
                for _ in range(self.cfg.compaction_max_jobs_per_drain):
                    self.checkpoint()
                    self._report("correspondence_compaction_jobs")
                    if not drain_compaction(conn, cfg=self.cfg, owner=self.owner):
                        break
            self._report(None)
            return result
        except Exception as exc:
            self._report(None, str(exc))
            raise
        finally:
            conn.close()

    def _recover_milestones(self, conn: Any) -> int:
        from nexus.agents.orrery.relationship_provenance import (
            emit_relationship_milestones_sync,
        )

        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT DISTINCT coalesce(v.source_chunk_id,
                    (SELECT max(chunk_id) FROM chunk_metadata WHERE world_layer = 'primary')) AS tick
                FROM relationship_milestone_queue q
                JOIN relationship_versions v ON v.id = q.version_id
                WHERE q.event_id IS NULL AND v.created_at <=
                    clock_timestamp() - (%s * interval '1 second')
                """,
                (self.cfg.milestone_recovery_age_seconds,),
            )
            ticks = [row["tick"] for row in cur.fetchall() if row["tick"] is not None]
            return sum(
                len(
                    emit_relationship_milestones_sync(
                        cur,
                        tick_chunk_id=tick,
                        recovery_age_seconds=self.cfg.milestone_recovery_age_seconds,
                    )[0]
                )
                for tick in ticks
            )

    def start(self) -> None:
        """Start an observer/owner loop; acquisition errors surface at startup."""
        owned = self.acquire()
        if owned:
            self._start_heartbeat()
        self._thread = threading.Thread(
            target=self._run,
            args=(owned,),
            name=f"scheduler-{self.dbname}",
            daemon=True,
        )
        self._thread.start()

    def _run(self, owned: bool) -> None:
        try:
            while not self.stopping.is_set():
                self.wakeup.clear()
                delay = self.cfg.poll_interval_seconds
                try:
                    if not owned:
                        owned = self.acquire()
                        if owned:
                            self._start_heartbeat()
                    if owned:
                        self._drain()
                except Exception:
                    logger.exception("Deferred-work pass failed for %s", self.dbname)
                    delay = self.cfg.error_backoff_seconds
                self.wakeup.wait(delay)
        except SchedulerStopped:
            pass
        finally:
            if owned:
                self._end_heartbeat()
                self.release()

    def stop(self) -> None:
        """Stop dispatch within the runtime grace; never cancel a provider call."""
        deadline = (
            time.monotonic() + self.settings["runtime"]["health"]["stop_grace_seconds"]
        )
        self.stopping.set()
        self.wakeup.set()
        if self._thread:
            self._thread.join(timeout=max(0, deadline - time.monotonic()))
        self._heartbeat_stop.set()
        # A request still in flight may finish under its domain nonce. It may
        # not issue another request; an expired domain lease is recoverable.
        self.release()
