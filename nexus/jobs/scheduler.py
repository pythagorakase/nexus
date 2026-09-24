"""One durable, preemptible recovery owner for each slot database."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4
from weakref import WeakSet

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from nexus.config import load_settings_as_dict
from nexus.config.settings_models import DeferredWorkSettings
from nexus.database import connection_kwargs
from nexus.jobs.gate import SchedulerStopped, provider_gate

logger = logging.getLogger(__name__)
_schedulers: WeakSet[SlotScheduler] = WeakSet()


def notify_generation_released(dbname: str) -> None:
    """Wake local owners immediately after a generation lease commits release."""
    for scheduler in list(_schedulers):
        if scheduler.dbname == dbname:
            scheduler.wakeup.set()


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
        self._lost = threading.Event()
        self.state = "observer"
        self.reason: str | None = None
        self.last_error: str | None = None
        self._job_lock = threading.RLock()
        self._job: dict[str, Any] | None = None
        self._waiting = False
        self._job_called = False
        self._job_lost = False
        self._lock_observed = False
        self._unlock_observed_at: float | None = None

    def connect(self) -> Any:
        """Open an independent connection to this scheduler's explicit database."""
        return psycopg2.connect(**connection_kwargs(self.dbname))

    def _observe_lock(self) -> None:
        self._lock_observed = True
        self._unlock_observed_at = None
        if self.reason != "slot locked":
            logger.info("Deferred-work observer for %s: slot locked", self.dbname)
        self.state = "observer"
        self.reason = "slot locked"
        self.last_error = None
        self._lost.set()
        self.wakeup.set()

    def _slot_locked(self) -> bool:
        # Match save_slots.is_slot_locked, using this scheduler's database.
        conn = self.connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT setconfig
                    FROM pg_db_role_setting s
                    JOIN pg_database d ON d.oid = s.setdatabase
                    WHERE d.datname = %s AND s.setrole = 0
                    """,
                    (self.dbname,),
                )
                row = cur.fetchone()
                locked = bool(
                    row and row[0] and "default_transaction_read_only=on" in row[0]
                )
        finally:
            conn.close()
        if locked:
            self._observe_lock()
        elif self._lock_observed:
            self.state = "observer"
            self.reason = "slot locked"
            self.last_error = None
            now = time.monotonic()
            if self._unlock_observed_at is None:
                self._unlock_observed_at = now
                logger.info(
                    "Deferred-work observer for %s: slot lock cleared; holding for %s seconds",
                    self.dbname,
                    self.cfg.unlock_hold_seconds,
                )
            if now - self._unlock_observed_at < self.cfg.unlock_hold_seconds:
                return True
            self._unlock_observed_at = None
            self._lock_observed = False
            self.reason = None
        return locked

    def acquire(self) -> bool:
        """Acquire only a vacant or expired singleton; never steal a live owner."""
        if self._slot_locked():
            return False
        nonce = str(uuid4())
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
                    (self.owner, nonce, self.cfg.lease_duration_seconds),
                )
                acquired = cur.fetchone() is not None
            if acquired:
                self.nonce = nonce
                self._lost.clear()
                self.state = "owner"
            elif self.state != "recovering":
                self.state = "observer"
            return acquired
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

    def _track_lease(self, queue: str, job_id: int, **lease: Any) -> None:
        with self._job_lock:
            self._job = {"queue": queue, "id": job_id, **lease}
            self._job_called = False
            self._job_lost = False

    def _renew_job(self) -> bool:
        # The local lock prevents a heartbeat from renewing an already-finished
        # checkpoint's job. The database lock protects the nonce and wall clock.
        with self._job_lock:
            if self._job is None:
                return True
            if self._job_lost:
                return False
            job = self._job
            conn = self.connect()
            try:
                with conn, conn.cursor() as cur:
                    cur.execute(
                        sql.SQL("SELECT id FROM {} WHERE id=%s FOR UPDATE").format(
                            sql.Identifier(job["queue"])
                        ),
                        (job["id"],),
                    )
                    cur.execute(
                        sql.SQL(
                            """
                        UPDATE {} SET lease_until=clock_timestamp() + (%s * interval '1 second')
                        WHERE id=%s AND state='leased' AND locked_by=%s AND lease_nonce=%s
                          AND lease_until > clock_timestamp()
                        """
                        ).format(sql.Identifier(job["queue"])),
                        (
                            job["duration"],
                            job["id"],
                            job["locked_by"],
                            job["lease_nonce"],
                        ),
                    )
                    live = cur.rowcount == 1
                self._job_lost = not live
                return live
            finally:
                conn.close()

    def _abandon_job(self) -> None:
        """Refund an unissued attempt only while its original nonce still matches."""
        with self._job_lock:
            if self._job is None:
                return
            job = self._job
            conn = self.connect()
            try:
                with conn, conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            """
                        UPDATE {} SET state='queued', lease_until=NULL,
                            locked_by=NULL, lease_nonce=NULL,
                            attempts=greatest(0, attempts-%s), updated_at=now()
                        WHERE id=%s AND state='leased' AND locked_by=%s AND lease_nonce=%s
                        """
                        ).format(sql.Identifier(job["queue"])),
                        (
                            0 if self._job_called else 1,
                            job["id"],
                            job["locked_by"],
                            job["lease_nonce"],
                        ),
                    )
            finally:
                conn.close()

    def checkpoint(self, *, provider: bool = False) -> None:
        """Wait for generation, keeping a selected job fenced and renewable."""
        with self._job_lock:
            self._waiting = True
        try:
            while not self.stopping.is_set() and not self._lost.is_set():
                # Clear before the query so a release between query and wait
                # cannot be lost. Cross-process releases use the poll fallback.
                self.wakeup.clear()
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
                    break
                if not self._renew_job():
                    self._abandon_job()
                    raise SchedulerStopped(
                        "Deferred job lease expired or changed before dispatch"
                    )
                if not generating:
                    if self.stopping.is_set() or self._lost.is_set():
                        break
                    if provider:
                        with self._job_lock:
                            self._job_called = True
                    return
                self.wakeup.wait(self.cfg.generation_wait_seconds)
            self._abandon_job()
            raise SchedulerStopped("Scheduler stopping or ownership lost")
        finally:
            with self._job_lock:
                self._waiting = False

    def _report(self, job: str | None, error: str | None = None) -> None:
        if job is None or ":" not in job:
            with self._job_lock:
                self._job = None
        conn = self.connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE deferred_work_scheduler SET current_job = %s, last_error = %s
                    WHERE id AND owner_id = %s AND lease_nonce = %s
                      AND expires_at > clock_timestamp()
                    """,
                    (job, error or self.last_error, self.owner, self.nonce),
                )
        finally:
            conn.close()

    def _recover(self, exc: BaseException) -> None:
        if isinstance(exc, psycopg2.errors.ReadOnlySqlTransaction):
            self._observe_lock()
            return
        if isinstance(exc, SchedulerStopped) and self.reason == "slot locked":
            return
        self.reason = None
        if self._lock_observed:
            self._unlock_observed_at = None
        # Never issue diagnostic SQL here: the database may be unreachable.
        if not self._lost.is_set():
            self.last_error = str(exc)
        self.state = "recovering"
        self._lost.set()
        self.wakeup.set()
        logger.error(
            "Deferred-work owner recovering for %s: %s", self.dbname, exc, exc_info=True
        )

    def _heartbeats(self) -> None:
        try:
            while not self._heartbeat_stop.wait(self.cfg.heartbeat_interval_seconds):
                if not self.renew():
                    raise RuntimeError("Scheduler heartbeat lost ownership")
                with self._job_lock:
                    if self._waiting and not self._renew_job():
                        self.wakeup.set()
        except Exception as exc:
            self._recover(exc)

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
        try:
            if not self.acquire():
                return {"owner": False, "drained": False}
            self._start_heartbeat()
            try:
                return self._drain(**limits)
            except psycopg2.errors.ReadOnlySqlTransaction as exc:
                self._recover(exc)
                return {"owner": False, "drained": False}
            except SchedulerStopped:
                if self.reason != "slot locked":
                    raise
                return {"owner": False, "drained": False}
            finally:
                self._end_heartbeat()
                if self.reason != "slot locked":
                    self.release()
        except psycopg2.errors.ReadOnlySqlTransaction as exc:
            self._recover(exc)
            return {"owner": False, "drained": False}

    def _drain(self, **limits: Any) -> dict[str, Any]:
        from nexus.agents.orrery import worker
        from nexus.agents.orrery.retrograde_maturation import drain_maturation_jobs_sync
        from nexus.jobs.compaction import drain_compaction

        result: dict[str, Any] = {"owner": True, "drained": True}
        conn = self.connect()
        try:
            with provider_gate(
                lambda: self.checkpoint(provider=True), self._report, self._track_lease
            ):
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
                        try:
                            counts = drain()
                        finally:
                            with self._job_lock:
                                self._job = None
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
                    try:
                        count = drain_compaction(conn, cfg=self.cfg, owner=self.owner)
                    finally:
                        with self._job_lock:
                            self._job = None
                    if not count:
                        break
            self._report(None)
            return result
        finally:
            with self._job_lock:
                self._job = None
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
        """Keep reacquiring after transient failures until shutdown is requested."""
        _schedulers.add(self)
        try:
            owned = self.acquire()
        except Exception as exc:
            self._recover(exc)
            owned = False
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
                if self._lost.is_set():
                    self._end_heartbeat()
                    owned = False
                    delay = (
                        self.cfg.poll_interval_seconds
                        if self.reason == "slot locked"
                        else self.cfg.error_backoff_seconds
                    )
                    if self.stopping.wait(delay):
                        break
                    self._lost.clear()
                self.wakeup.clear()
                try:
                    if not owned:
                        owned = self.acquire()
                        if owned:
                            self._start_heartbeat()
                    if owned:
                        self._drain()
                except (Exception, SchedulerStopped) as exc:
                    if not self.stopping.is_set():
                        self._recover(exc)
                    continue
                if not self._lost.is_set():
                    self.wakeup.wait(self.cfg.poll_interval_seconds)
        finally:
            self._end_heartbeat()
            if owned and not self._lost.is_set():
                try:
                    self.release()
                except Exception as exc:
                    self._recover(exc)

    def stop(self) -> None:
        """Stop dispatch within the runtime grace; never cancel a provider call."""
        deadline = (
            time.monotonic() + self.settings["runtime"]["health"]["stop_grace_seconds"]
        )
        _schedulers.discard(self)
        self.stopping.set()
        self.wakeup.set()
        if self._thread:
            self._thread.join(timeout=max(0, deadline - time.monotonic()))
        self._heartbeat_stop.set()
        if self.state == "owner" and not self._lost.is_set():
            try:
                self.release()
            except Exception as exc:
                self._recover(exc)
