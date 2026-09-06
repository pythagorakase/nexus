"""Real-PostgreSQL job fences (#676) and provider retirement (#846)."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any, Iterator, Mapping
from uuid import uuid4

import psycopg2
import pytest
from psycopg2 import sql
from psycopg2.errors import UniqueViolation
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from nexus.agents.orrery import worker
from nexus.agents.orrery.bleed import load_bleed_candidates, record_bleed_uptake_sync
from nexus.agents.orrery.events import commit_orrery_tick_sync
from nexus.agents.orrery.resolver import resolve_dry_run
from nexus.agents.orrery.templates import BUILTIN_TEMPLATES
from nexus.agents.orrery.worker import (
    drain_narration_outbox_sync,
    promote_pending_resolutions_sync,
)


pytestmark = pytest.mark.requires_postgres

ROOT = Path(__file__).parents[2]
MIGRATION_SQL = (ROOT / "migrations" / "102_narration_job_fencing.sql").read_text()


class _BlockingDescriptor:
    """Pause the first real descriptor build to exercise database lease races."""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.build = worker._perceptual_descriptor

    def __call__(self, row: Mapping[str, Any]) -> dict[str, Any]:
        if not self.started.is_set():
            self.started.set()
            if not self.release.wait(timeout=10):
                raise TimeoutError("test did not release the original worker")
        return self.build(row)


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


def _settings(*, lease_duration_seconds: int = 60) -> dict[str, Any]:
    """Return deterministic narration worker settings for database tests."""

    return {
        "orrery": {
            "narration": {
                "max_attempts": 3,
                "retry_delay_seconds": 0,
                "lease_duration_seconds": lease_duration_seconds,
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
    cur.execute(
        "UPDATE chunk_metadata SET world_time = %s WHERE chunk_id = %s",
        (datetime(2196, 7, 6, 23, 0, tzinfo=timezone.utc), chunk_id),
    )
    return chunk_id


def _materialize_pending_resolution(conn: Any, *, label: str) -> tuple[int, int]:
    """Resolve and commit a genuine Orrery proposal at a narrative anchor."""

    with conn.cursor() as cur:
        chunk_id = _insert_chunk(cur, f"Issue 676 anchor: {label}")
        cur.execute("INSERT INTO entities (kind) VALUES ('character') RETURNING id")
        actor_id = int(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO characters (name, entity_id) VALUES (%s, %s)",
            (f"Courier {label}", actor_id),
        )
        cur.execute(
            """
            UPDATE character_need_states
            SET debt_score = 60,
                last_evaluated_at = %s
            WHERE character_entity_id = %s
              AND need_type = 'sleep'
            """,
            (datetime(2196, 7, 6, 23, 0, tzinfo=timezone.utc), actor_id),
        )
        assert cur.rowcount == 1, "Character trigger did not initialize sleep debt"
        cur.execute(
            """
            INSERT INTO world_events (
                event_type, tick_chunk_id, actor_entity_id,
                world_layer, source, changed_fields, payload
            ) VALUES (
                'slept', %s, %s, 'primary', 'resolver', '{}', '{}'::jsonb
            )
            """,
            (chunk_id, actor_id),
        )
    conn.commit()

    engine = create_engine(
        URL.create(
            "postgresql+psycopg2",
            username=os.environ.get("PGUSER", "pythagor"),
            host=os.environ.get("PGHOST", "localhost"),
            port=int(os.environ.get("PGPORT", "5432")),
            database=conn.info.dbname,
        ),
        future=True,
    )
    try:
        with Session(engine) as session:
            proposal = resolve_dry_run(
                session,
                BUILTIN_TEMPLATES,
                anchor_chunk_id=chunk_id,
                window_chunks=30,
                epistemics_settings={"enabled": False},
            )
    finally:
        engine.dispose()

    assert proposal.resolutions, (
        "Genuine Orrery resolver produced no draft for the seeded high sleep debt; "
        f"actor={actor_id}, chunk={chunk_id}"
    )
    assert proposal.actor_count == 1
    assert len(proposal.resolutions) == 1, (
        "Issue 676 fixture must resolve exactly one deterministic draft; got "
        f"{[draft.template_id for draft in proposal.resolutions]}"
    )
    draft = proposal.resolutions[0]
    assert draft.template_id == "sleep", (
        "Seeded high sleep debt must resolve through the real SLEEP package; got "
        f"{draft.template_id}"
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
            (draft.binding_hash,),
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


def _drain(
    dbname: str,
    *,
    lease_duration_seconds: int = 60,
) -> tuple[int, int]:
    """Run the public narration drain with its own worker connection."""

    conn = _connect(dbname)
    try:
        return drain_narration_outbox_sync(
            slot=676,
            settings=_settings(lease_duration_seconds=lease_duration_seconds),
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


def test_expired_lease_reclaimed_and_original_completion_fenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

        original_descriptor = _BlockingDescriptor()
        monkeypatch.setattr(worker, "_perceptual_descriptor", original_descriptor)
        with ThreadPoolExecutor(max_workers=2) as executor:
            original = executor.submit(_drain, dbname)
            assert original_descriptor.started.wait(timeout=10)

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

            reclaimed = executor.submit(_drain, dbname)
            assert reclaimed.result(timeout=10) == (1, 0)
            original_descriptor.release.set()
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
    """A resolution retargeted after enqueue cannot publish an off-screen descriptor."""

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

        assert _drain(dbname) == (0, 1)

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


def test_completion_locks_world_layer_before_comparing_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A concurrent layer update wins before completion and rejects a stale descriptor."""

    with _disposable_narration_db() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                resolution_id, anchor_chunk = _materialize_pending_resolution(
                    conn, label="layer-lock"
                )
            _enqueue(conn, resolution_id)
        finally:
            conn.close()

        descriptor = _BlockingDescriptor()
        monkeypatch.setattr(worker, "_perceptual_descriptor", descriptor)
        with ThreadPoolExecutor(max_workers=1) as executor:
            completion = executor.submit(_drain, dbname)
            assert descriptor.started.wait(timeout=10)

            layer_writer = _connect(dbname)
            try:
                with layer_writer.cursor() as cur:
                    cur.execute(
                        "UPDATE chunk_metadata SET world_layer = 'flashback' "
                        "WHERE chunk_id = %s",
                        (anchor_chunk,),
                    )
                    assert cur.rowcount == 1
                descriptor.release.set()
                assert Event().wait(timeout=0.2) is False
                assert not completion.done()
                layer_writer.commit()
            finally:
                layer_writer.close()

            assert completion.result(timeout=10) == (0, 1)

        conn = _connect(dbname)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT j.state::text, cm.world_layer::text, count(n.id) "
                    "FROM orrery_narration_jobs AS j "
                    "JOIN orrery_resolutions AS r ON r.id = j.resolution_id "
                    "JOIN chunk_metadata AS cm ON cm.chunk_id = r.tick_chunk_id "
                    "LEFT JOIN offscreen_narrations AS n "
                    "ON n.resolution_id = r.id "
                    "WHERE r.id = %s "
                    "GROUP BY j.state, cm.world_layer",
                    (resolution_id,),
                )
                assert cur.fetchone() == ("stale_rejected", "flashback", 0)
        finally:
            conn.close()


def test_completion_clock_counts_time_blocked_on_job_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lease that expires during lock wait cannot complete with stale now()."""

    with _disposable_narration_db() as dbname:
        conn = _connect(dbname)
        try:
            with conn:
                resolution_id, _ = _materialize_pending_resolution(
                    conn, label="wall-clock-expiry"
                )
            _enqueue(conn, resolution_id)
        finally:
            conn.close()

        descriptor = _BlockingDescriptor()
        monkeypatch.setattr(worker, "_perceptual_descriptor", descriptor)
        with ThreadPoolExecutor(max_workers=1) as executor:
            completion = executor.submit(
                _drain,
                dbname,
                lease_duration_seconds=1,
            )
            assert descriptor.started.wait(timeout=10)

            job_locker = _connect(dbname)
            try:
                with job_locker.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM orrery_narration_jobs "
                        "WHERE resolution_id = %s FOR UPDATE",
                        (resolution_id,),
                    )
                    assert cur.fetchone() is not None
                descriptor.release.set()
                assert Event().wait(timeout=1.2) is False
                job_locker.commit()
            finally:
                job_locker.close()

            assert completion.result(timeout=10) == (0, 1)

        conn = _connect(dbname)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT state::text, lease_until < clock_timestamp() "
                    "FROM orrery_narration_jobs WHERE resolution_id = %s",
                    (resolution_id,),
                )
                assert cur.fetchone() == ("leased", True)
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

        assert _drain(dbname) == (1, 0)

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


def test_descriptor_retirement_preserves_canon_legacy_jobs_and_bleed(
    monkeypatch,
) -> None:
    """Real resolve-to-Bleed flow costs no provider call and retains audit facts.

    Uses narrative_chunks, chunk_metadata, entities, characters, need state,
    world_events, resolutions, and the durable off-screen tables in a disposable
    migrated template clone. No real slot is read, drained, or changed.
    """
    from nexus.telemetry import usage
    from scripts.api_anthropic import AnthropicProvider
    from scripts.api_openai import OpenAIProvider

    def forbid_provider(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Deterministic off-screen records must never call a provider")

    monkeypatch.setattr(AnthropicProvider, "get_completion", forbid_provider)
    monkeypatch.setattr(OpenAIProvider, "get_completion", forbid_provider)

    with _disposable_narration_db() as dbname:
        conn = _connect(dbname)
        try:
            resolution_id, anchor = _materialize_pending_resolution(
                conn, label="descriptor-retirement"
            )
            _enqueue(conn, resolution_id)
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT provider, model_ref FROM orrery_narration_jobs "
                        "WHERE resolution_id = %s",
                        (resolution_id,),
                    )
                    assert cur.fetchone() == (None, None)
                    cur.execute(
                        "SELECT brief, state_delta, event_ids, promotion_verdict "
                        "FROM orrery_resolutions WHERE id = %s",
                        (resolution_id,),
                    )
                    canonical_before = cur.fetchone()
                    cur.execute(
                        "SELECT jsonb_agg(to_jsonb(e) ORDER BY id) FROM world_events e"
                    )
                    events_before = cur.fetchone()[0]
                    cur.execute("SELECT count(*) FROM narrative_chunks")
                    chunks_before = cur.fetchone()[0]
                    # Simulate a provider-era job still owned by an old worker.
                    # Its provenance and active lease must survive the new drain.
                    cur.execute(
                        "UPDATE orrery_narration_jobs SET state = 'leased', "
                        "provider = 'retired-provider', model_ref = 'retired-model', "
                        "locked_by = 'old-worker', lease_nonce = %s, "
                        "lease_until = clock_timestamp() + interval '1 hour', "
                        "attempts = 1 WHERE resolution_id = %s",
                        (str(uuid4()), resolution_id),
                    )
            assert _drain(dbname) == (0, 0)
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT state::text, locked_by, attempts "
                        "FROM orrery_narration_jobs WHERE resolution_id = %s",
                        (resolution_id,),
                    )
                    assert cur.fetchone() == ("leased", "old-worker", 1)
                    cur.execute(
                        "UPDATE orrery_narration_jobs "
                        "SET lease_until = clock_timestamp() - interval '1 second' "
                        "WHERE resolution_id = %s",
                        (resolution_id,),
                    )
            assert _drain(dbname) == (1, 0)
            assert _drain(dbname) == (0, 0)
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT brief, state_delta, event_ids, promotion_verdict "
                        "FROM orrery_resolutions WHERE id = %s",
                        (resolution_id,),
                    )
                    assert cur.fetchone() == canonical_before
                    cur.execute(
                        "SELECT jsonb_agg(to_jsonb(e) ORDER BY id) FROM world_events e"
                    )
                    assert cur.fetchone()[0] == events_before
                    cur.execute("SELECT count(*) FROM narrative_chunks")
                    assert cur.fetchone()[0] == chunks_before
                    cur.execute(
                        "SELECT text, perceptual_descriptor, embedding_status::text "
                        "FROM offscreen_narrations WHERE resolution_id = %s",
                        (resolution_id,),
                    )
                    record_text, descriptor, embedding_status = cur.fetchone()
                    assert json.loads(record_text) == descriptor
                    assert descriptor == {
                        "record_kind": "deterministic_descriptor",
                        "brief": canonical_before[0],
                        "summary": canonical_before[3]["perceptual_summary"],
                        "channel": canonical_before[3]["perceptual_channel"],
                    }
                    assert embedding_status == "pending"
                    cur.execute(
                        "SELECT state::text, attempts, provider, model_ref "
                        "FROM orrery_narration_jobs WHERE resolution_id = %s",
                        (resolution_id,),
                    )
                    assert cur.fetchone() == (
                        "succeeded",
                        2,
                        "retired-provider",
                        "retired-model",
                    )

            engine = create_engine(
                "postgresql+psycopg2://", creator=lambda: _connect(dbname)
            )
            try:
                with Session(engine) as session:
                    candidates = load_bleed_candidates(
                        session,
                        anchor_chunk_id=anchor,
                        density=1.0,
                        limit=5,
                    )
                    assert len(candidates) == 1
                    candidate = candidates[0]
                    assert candidate.resolution_id == resolution_id
                    assert candidate.summary == descriptor["summary"]
                    assert "text" not in candidate.model_dump()
                    menu_before = candidate.to_prompt_dict()

                # Preserve provider-era prose as audit material and prove it
                # cannot change the menu or uptake when its prose differs
                # entirely from the perceptual cue and current player text.
                legacy_text = (
                    "Unrelated legacy prose that must stay byte-for-byte intact."
                )
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE offscreen_narrations SET text = %s, "
                            "perceptual_descriptor = perceptual_descriptor - 'record_kind' "
                            "WHERE resolution_id = %s",
                            (legacy_text, resolution_id),
                        )
                assert _drain(dbname) == (0, 0)
                with Session(engine) as session:
                    legacy_candidate = load_bleed_candidates(
                        session,
                        anchor_chunk_id=anchor,
                        density=1.0,
                        limit=5,
                    )[0]
                    assert legacy_candidate.to_prompt_dict() == menu_before
                with conn:
                    assert (
                        record_bleed_uptake_sync(
                            conn,
                            resolution_ids=[resolution_id],
                            accepted_chunk_id=anchor,
                            accepted_text=f"{candidate.actor_name} slept.",
                        )
                        == 1
                    )
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT text FROM offscreen_narrations WHERE resolution_id = %s",
                            (resolution_id,),
                        )
                        assert cur.fetchone()[0] == legacy_text
            finally:
                engine.dispose()
            assert not list(usage._config.usage_dir.rglob("*.jsonl"))
        finally:
            conn.close()
