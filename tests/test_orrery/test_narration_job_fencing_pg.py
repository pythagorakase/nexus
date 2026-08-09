"""Real-PostgreSQL narration job fencing regressions for issue #676."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
from threading import Event
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.errors import UniqueViolation
import pytest

from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.resolver import OrreryResolutionDraft, OrreryTickProposal
from nexus.agents.orrery.worker import (
    drain_narration_outbox_sync,
    promote_pending_resolutions_sync,
)


pytestmark = pytest.mark.requires_postgres

ROOT = Path(__file__).parents[2]
MIGRATION_SQL = (ROOT / "migrations" / "102_narration_job_fencing.sql").read_text()


class _ProviderResponse:
    content = "The courier slips through the rain and disappears below the viaduct."


class _ImmediateProvider:
    """Deterministic provider double used after the genuine database lease."""

    def get_completion(self, _prompt: str) -> _ProviderResponse:
        return _ProviderResponse()


class _BlockingProvider:
    """Provider double that holds one worker outside its lease transaction."""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()

    def get_completion(self, _prompt: str) -> _ProviderResponse:
        self.started.set()
        if not self.release.wait(timeout=10):
            raise TimeoutError("test did not release the original narration worker")
        return _ProviderResponse()


def _connect(dbname: str) -> Any:
    """Open a PostgreSQL connection to a disposable issue-676 clone."""

    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        connect_timeout=2,
    )


@contextmanager
def _disposable_narration_db() -> Iterator[str]:
    """Yield a migrated NEXUS_template clone and always drop it afterward."""

    dbname = f"qa676_{uuid4().hex[:12]}"
    source_db = os.environ.get("NEXUS_TEST_TEMPLATE_DB", "NEXUS_template")
    assert source_db == "NEXUS_template" or source_db.startswith("qa676_")
    admin: Any = None
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier(source_db),
                )
            )
        conn = _connect(dbname)
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(MIGRATION_SQL)
        finally:
            conn.close()
        yield dbname
    finally:
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


def _settings() -> dict[str, Any]:
    """Return deterministic narration worker settings for database tests."""

    return {
        "orrery": {
            "narration": {
                "provider": "anthropic",
                "model_ref": "test-narrator",
                "max_attempts": 3,
                "retry_delay_seconds": 0,
                "lease_duration_seconds": 60,
                "max_jobs_per_drain": 5,
            },
            "promote": {
                "priority_threshold": 30.0,
                "magnitude_threshold": 0.35,
                "perceptual_summary_max_chars": 240,
            },
        }
    }


def _insert_chunk(cur: Any, label: str, *, world_layer: str = "primary") -> int:
    """Insert one real narrative anchor and its timeline metadata."""

    cur.execute(
        "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
        "VALUES (%s, %s) RETURNING id",
        (label, label),
    )
    chunk_id = int(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO chunk_metadata (chunk_id, world_layer) VALUES (%s, %s)",
        (chunk_id, world_layer),
    )
    return chunk_id


def _materialize_pending_resolution(conn: Any, *, label: str) -> tuple[int, int]:
    """Commit a real Orrery proposal at a narrative chunk anchor."""

    with conn.cursor() as cur:
        chunk_id = _insert_chunk(cur, f"Issue 676 anchor: {label}")
        cur.execute("INSERT INTO entities (kind) VALUES ('character') RETURNING id")
        actor_id = int(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO characters (name, entity_id) VALUES (%s, %s)",
            (f"Courier {label}", actor_id),
        )

    binding_hash = f"issue-676-{label}-{uuid4()}"
    draft = OrreryResolutionDraft(
        template_id="hide",
        priority=80,
        binding_hash=binding_hash,
        bindings={"actor": actor_id},
        binding_names={"actor": f"Courier {label}"},
        branch_label="Issue 676 narration fencing probe",
        narrative_stub="{actor} disappears below the viaduct.",
        magnitude=0.72,
    )
    proposal = OrreryTickProposal(
        anchor_chunk_id=chunk_id,
        actor_count=1,
        resolutions=(draft,),
    )
    result = commit_orrery_tick_sync(
        conn,
        proposal,
        tick_chunk_id=chunk_id,
        slot=676,
    )
    assert result.resolution_count == 1
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM orrery_resolutions WHERE binding_hash = %s",
            (binding_hash,),
        )
        return int(cur.fetchone()[0]), chunk_id


def _enqueue(conn: Any, resolution_id: int) -> None:
    """Drive the public promotion entry point and prove it enqueued the target."""

    promoted, skipped = promote_pending_resolutions_sync(
        slot=676,
        settings=_settings(),
        conn=conn,
    )
    assert (promoted, skipped) == (1, 0)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM orrery_narration_jobs WHERE resolution_id = %s",
            (resolution_id,),
        )
        assert int(cur.fetchone()[0]) == 1


def _drain(dbname: str, provider: Any) -> tuple[int, int]:
    """Run the public narration drain with its own worker connection."""

    conn = _connect(dbname)
    try:
        return drain_narration_outbox_sync(
            slot=676,
            settings=_settings(),
            narration_provider=provider,
            conn=conn,
        )
    finally:
        conn.close()


def test_duplicate_enqueue_collapses_to_one_effective_job() -> None:
    """Repeated genuine promotion delivery cannot create a second active job."""

    with _disposable_narration_db() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                resolution_id, _ = _materialize_pending_resolution(
                    conn, label="duplicate-enqueue"
                )
            _enqueue(conn, resolution_id)
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE orrery_resolutions "
                        "SET promotion_status = 'pending' WHERE id = %s",
                        (resolution_id,),
                    )
            _enqueue(conn, resolution_id)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM orrery_narration_jobs "
                    "WHERE resolution_id = %s AND superseded_at IS NULL",
                    (resolution_id,),
                )
                assert int(cur.fetchone()[0]) == 1
        finally:
            conn.close()


def test_expired_lease_reclaimed_and_original_completion_fenced() -> None:
    """A reclaimer wins once and the original owner's late output is rejected."""

    with _disposable_narration_db() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                resolution_id, _ = _materialize_pending_resolution(
                    conn, label="expired-lease"
                )
            _enqueue(conn, resolution_id)
        finally:
            conn.close()

        original_provider = _BlockingProvider()
        with ThreadPoolExecutor(max_workers=2) as executor:
            original = executor.submit(_drain, dbname, original_provider)
            assert original_provider.started.wait(timeout=10)

            conn = _connect(dbname)
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE orrery_narration_jobs "
                            "SET lease_until = now() - interval '1 second' "
                            "WHERE resolution_id = %s AND state = 'leased'",
                            (resolution_id,),
                        )
                        assert cur.rowcount == 1
            finally:
                conn.close()

            reclaimed = executor.submit(_drain, dbname, _ImmediateProvider())
            assert reclaimed.result(timeout=10) == (1, 0)
            original_provider.release.set()
            assert original.result(timeout=10) == (0, 1)

        conn = _connect(dbname)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT state::text, attempts, locked_by, lease_nonce "
                    "FROM orrery_narration_jobs WHERE resolution_id = %s",
                    (resolution_id,),
                )
                assert cur.fetchone() == ("succeeded", 2, None, None)
                cur.execute(
                    "SELECT count(*) FROM offscreen_narrations "
                    "WHERE resolution_id = %s",
                    (resolution_id,),
                )
                assert int(cur.fetchone()[0]) == 1
        finally:
            conn.close()


def test_stale_anchor_completion_is_terminally_rejected() -> None:
    """A resolution retargeted after enqueue cannot publish generated prose."""

    with _disposable_narration_db() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                resolution_id, original_chunk = _materialize_pending_resolution(
                    conn, label="stale-anchor"
                )
            _enqueue(conn, resolution_id)
            with conn:
                with conn.cursor() as cur:
                    replacement_chunk = _insert_chunk(
                        cur, "Replacement timeline anchor"
                    )
                    cur.execute(
                        "UPDATE orrery_resolutions "
                        "SET tick_chunk_id = %s WHERE id = %s",
                        (replacement_chunk, resolution_id),
                    )
        finally:
            conn.close()

        assert _drain(dbname, _ImmediateProvider()) == (0, 1)

        conn = _connect(dbname)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT state::text, anchor_tick_chunk_id, last_error "
                    "FROM orrery_narration_jobs WHERE resolution_id = %s",
                    (resolution_id,),
                )
                state, anchor_chunk, error = cur.fetchone()
                assert state == "stale_rejected"
                assert int(anchor_chunk) == original_chunk
                assert "anchor changed" in error
                cur.execute(
                    "SELECT count(*) FROM offscreen_narrations "
                    "WHERE resolution_id = %s",
                    (resolution_id,),
                )
                assert int(cur.fetchone()[0]) == 0
        finally:
            conn.close()


def test_normal_narration_path_succeeds_once_end_to_end() -> None:
    """The genuine enqueue, lease, and completion path remains successful."""

    with _disposable_narration_db() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                resolution_id, _ = _materialize_pending_resolution(
                    conn, label="normal-path"
                )
            _enqueue(conn, resolution_id)
        finally:
            conn.close()

        assert _drain(dbname, _ImmediateProvider()) == (1, 0)

        conn = _connect(dbname)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT j.state::text, r.narration_status::text, n.id "
                    "FROM orrery_narration_jobs AS j "
                    "JOIN orrery_resolutions AS r ON r.id = j.resolution_id "
                    "JOIN offscreen_narrations AS n ON n.resolution_id = r.id "
                    "WHERE r.id = %s",
                    (resolution_id,),
                )
                state, narration_status, _narration_id = cur.fetchone()
                assert (state, narration_status) == ("succeeded", "succeeded")

            with pytest.raises(UniqueViolation):
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO offscreen_narrations (
                                resolution_id, tick_chunk_id, text
                            )
                            SELECT id, tick_chunk_id, 'duplicate output'
                            FROM orrery_resolutions
                            WHERE id = %s
                            """,
                            (resolution_id,),
                        )
        finally:
            conn.close()
