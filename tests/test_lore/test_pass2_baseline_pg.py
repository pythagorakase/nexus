"""Ephemeral-PostgreSQL lifecycle coverage for durable Pass-2 baselines."""

from __future__ import annotations

import asyncio
import copy
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
from uuid import uuid4

import psycopg2
import pytest
from psycopg2 import sql
from sqlalchemy import create_engine, text

from nexus.agents.logon.apex_schema import StorytellerResponseStandard
from nexus.api import commit_handler_sync
from nexus.api.commit_handler_sync import commit_incubator_to_database_sync
from nexus.api.lore_adapter import response_to_incubator
from nexus.api.narrative_generation import write_to_incubator
from nexus.memory.manager import ContextMemoryManager, MissingPass2BaselineError
from scripts import stamp_lore_pass_baseline


pytestmark = pytest.mark.requires_postgres

MIGRATION = Path("migrations/107_lore_pass_baselines.sql")


def _connect(dbname: str) -> Any:
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )


@pytest.fixture()
def pass2_database() -> Iterator[str]:
    """Clone the template, apply migration 107, and always drop the clone."""

    dbname = f"nexus_test_pass2_{uuid4().hex[:12]}"
    source_db = os.environ.get("NEXUS_TEST_TEMPLATE_DB", "NEXUS_template")
    admin = _connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(dbname),
                    sql.Identifier(source_db),
                )
            )
        migration = MIGRATION.read_text()
        with _connect(dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(migration)
                cur.execute(migration)
                cur.execute("DELETE FROM incubator")
                cur.execute("DELETE FROM narrative_generation_lease")
                cur.execute("DELETE FROM narrative_generation_sessions")
        yield dbname
    finally:
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
    return {
        "Agent Settings": {
            "LORE": {
                "token_budget": {
                    "apex_context_window": 1_000,
                    "provider_overrides": {},
                }
            }
        },
        "memory": {
            "phase2_fraction": 0.1,
            "raw_search_k": 30,
            "skip_simple_choices": False,
            "pass2_budget_reserve": 0.25,
            "divergence_threshold": 0.7,
            "warm_slice_default": True,
            "max_sql_iterations": 5,
        },
    }


class _DatabaseMemnon:
    """Minimal MEMNON surface backed by the disposable database engine."""

    def __init__(self, engine: Any, results: list[dict[str, Any]] | None = None):
        self.db_manager = SimpleNamespace(engine=engine)
        self.idf_dictionary = None
        self.results = results or []

    def query_memory(
        self, query: str, k: int = 5, use_hybrid: bool = True
    ) -> dict[str, Any]:
        del query, k, use_hybrid
        return {"results": copy.deepcopy(self.results)}


def _seed_parent(conn: Any, label: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO narrative_chunks (raw_text, storyteller_text)
            VALUES (%s, %s)
            RETURNING id
            """,
            (label, label),
        )
        chunk_id = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO chunk_metadata (
                chunk_id, season, episode, scene, world_layer, slug
            ) VALUES (%s, 1, 1, 1, 'primary', %s)
            """,
            (chunk_id, f"pass2-{chunk_id}"),
        )
    return chunk_id


def _create_lease(conn: Any, session_id: str, parent_chunk_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO narrative_generation_sessions (
                session_id, operation, parent_chunk_id, status
            ) VALUES (%s, 'continue', %s, 'initiated')
            """,
            (session_id, parent_chunk_id),
        )
        cur.execute(
            """
            INSERT INTO narrative_generation_lease (
                id, session_id, parent_chunk_id, operation, expires_at
            ) VALUES (TRUE, %s, %s, 'continue', NOW() + INTERVAL '5 minutes')
            """,
            (session_id, parent_chunk_id),
        )


def _replace_lease(conn: Any, session_id: str, parent_chunk_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM narrative_generation_lease")
    _create_lease(conn, session_id, parent_chunk_id)


def _response(narrative: str) -> StorytellerResponseStandard:
    return StorytellerResponseStandard.model_validate(
        {
            "generation_model": "TEST",
            "narrative": narrative,
            "choices": ["Continue.", "Wait."],
            "chunk_metadata": {
                "chronology": {"episode_transition": "continue"},
                "world_layer": "primary",
            },
            "referenced_entities": {
                "characters": [],
                "places": [],
                "factions": [],
            },
            "state_updates": {
                "characters": [],
                "locations": [],
                "factions": [],
                "relationships": [],
            },
        }
    )


def _patch_unrelated_commit_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        commit_handler_sync,
        "commit_orrery_tick_sync",
        lambda *_args, **_kwargs: SimpleNamespace(
            resolution_count=0,
            event_count=0,
            tag_mutation_count=0,
            cleared_tag_count=0,
            skipped_existing_count=0,
            adjudication_count=0,
            deferred_count=0,
            voided_count=0,
            replaced_count=0,
            scene_pressure_count=0,
            prompt_exposure_count=0,
            propagation_count=0,
            reveal_count=0,
        ),
    )
    monkeypatch.setattr(
        commit_handler_sync, "_orrery_checkpoint_interval", lambda _settings: 0
    )
    monkeypatch.setattr(
        "nexus.api.presence_audit.presence_audit_enabled", lambda: False
    )


def test_two_turn_regeneration_sparse_promotion_restore_and_cascade(
    pass2_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepted turn N restores exact exclusions in a fresh manager for N+1."""

    _patch_unrelated_commit_work(monkeypatch)
    database_url = f"postgresql://{os.environ.get('PGUSER', 'pythagor')}@"
    database_url += (
        f"{os.environ.get('PGHOST', 'localhost')}:"
        f"{os.environ.get('PGPORT', '5432')}/{pass2_database}"
    )
    engine = create_engine(database_url, future=True)
    conn = _connect(pass2_database)
    try:
        parent_chunk_id = _seed_parent(conn, "accepted parent")
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO narrative_chunks (raw_text, storyteller_text) "
                "VALUES ('retired', 'retired') RETURNING id"
            )
            retired_id = int(cur.fetchone()[0])
            cur.execute("DELETE FROM narrative_chunks WHERE id = %s", (retired_id,))

        manager_n = ContextMemoryManager(_settings(), memnon=_DatabaseMemnon(engine))
        manager_n.handle_storyteller_response(
            narrative="Provisional first generation.",
            warm_slice=[{"chunk_id": parent_chunk_id, "text": "accepted parent"}],
            retrieved_passages=[
                {
                    "memory_id": "retrograde_summary:7",
                    "content_type": "retrograde_summary",
                    "text": "summary",
                }
            ],
            token_usage={
                "total_available": 100,
                "warm_slice": 10,
                "structured": 0,
                "augmentation": 0,
            },
            assembled_context={
                "warm_slice": {"chunks": []},
                "retrieved_passages": {"results": []},
            },
        )
        first_baseline = manager_n.export_pass2_baseline()

        first_session = str(uuid4())
        _create_lease(conn, first_session, parent_chunk_id)
        conn.commit()
        first_payload = response_to_incubator(
            _response("Provisional first generation."),
            parent_chunk_id=parent_chunk_id,
            user_text="Continue.",
            session_id=first_session,
            lore_pass_baseline=first_baseline,
        )
        asyncio.run(write_to_incubator(conn, first_payload))

        second_baseline = first_baseline.model_copy(
            update={"memory_identities": [parent_chunk_id, 999_998]}
        )
        second_session = str(uuid4())
        _replace_lease(conn, second_session, parent_chunk_id)
        conn.commit()
        second_payload = response_to_incubator(
            _response("Replacement generation."),
            parent_chunk_id=parent_chunk_id,
            user_text="Continue.",
            session_id=second_session,
            lore_pass_baseline=second_baseline,
        )
        asyncio.run(
            write_to_incubator(
                conn,
                second_payload,
                expected_incubator_session=first_session,
            )
        )
        with conn.cursor() as cur:
            cur.execute("SELECT storyteller_text, lore_pass_baseline FROM incubator")
            staged_text, staged_baseline = cur.fetchone()
        assert staged_text == "Replacement generation."
        assert staged_baseline["memory_identities"] == [parent_chunk_id, 999_998]

        accepted_chunk_id = commit_incubator_to_database_sync(
            conn, second_session, slot=5
        )
        assert accepted_chunk_id > parent_chunk_id + 1
        with engine.connect() as read_conn:
            rows = read_conn.execute(
                text(
                    "SELECT chunk_id, payload FROM lore_pass_baselines "
                    "WHERE chunk_id >= :parent ORDER BY chunk_id"
                ),
                {"parent": parent_chunk_id},
            ).all()
        assert [row[0] for row in rows] == [accepted_chunk_id]
        assert rows[0][1]["parent_chunk_id"] == accepted_chunk_id

        fresh_memnon = _DatabaseMemnon(
            engine,
            results=[
                {"chunk_id": parent_chunk_id, "text": "duplicate parent"},
                {"chunk_id": 999_998, "text": "duplicate retrieval"},
                {"chunk_id": 999_999, "text": "new memory"},
            ],
        )
        manager_n_plus_one = ContextMemoryManager(_settings(), memnon=fresh_memnon)
        restored = manager_n_plus_one.restore_pass2_baseline(accepted_chunk_id)
        manager_n_plus_one.configure_base_storyteller_budget()
        update = manager_n_plus_one.handle_user_input("Investigate Zyxonium")
        assert restored.memory_identities == [parent_chunk_id, 999_998]
        assert update.baseline_available is True
        assert [row["chunk_id"] for row in update.retrieved_chunks] == [999_999]

        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM narrative_chunks WHERE id = %s", (accepted_chunk_id,)
            )
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM lore_pass_baselines WHERE chunk_id = %s",
                (accepted_chunk_id,),
            )
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()
        engine.dispose()


def test_acceptance_failure_rolls_back_chunk_baseline_and_incubator_delete(
    pass2_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A post-baseline acceptance failure leaves only the provisional row."""

    _patch_unrelated_commit_work(monkeypatch)
    conn = _connect(pass2_database)
    try:
        parent_chunk_id = _seed_parent(conn, "rollback parent")
        session_id = str(uuid4())
        _create_lease(conn, session_id, parent_chunk_id)
        conn.commit()
        baseline = ContextMemoryManager(_settings()).handle_storyteller_response(
            narrative="Rollback candidate.",
            warm_slice=[{"chunk_id": parent_chunk_id, "text": "parent"}],
            token_usage={"total_available": 50, "warm_slice": 10},
        )
        assert baseline.baseline_chunks == {parent_chunk_id}
        staged = ContextMemoryManager(_settings())
        staged.handle_storyteller_response(
            narrative="Rollback candidate.",
            warm_slice=[{"chunk_id": parent_chunk_id, "text": "parent"}],
            token_usage={"total_available": 50, "warm_slice": 10},
        )
        payload = response_to_incubator(
            _response("Rollback candidate."),
            parent_chunk_id=parent_chunk_id,
            user_text="Continue.",
            session_id=session_id,
            lore_pass_baseline=staged.export_pass2_baseline(),
        )
        asyncio.run(write_to_incubator(conn, payload))
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM narrative_chunks")
            before_chunks = int(cur.fetchone()[0])

        monkeypatch.setattr(
            commit_handler_sync,
            "insert_chunk_metadata_sync",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("forced metadata failure")
            ),
        )
        with pytest.raises(RuntimeError, match="forced metadata failure"):
            commit_incubator_to_database_sync(conn, session_id, slot=5)

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM narrative_chunks")
            assert cur.fetchone()[0] == before_chunks
            cur.execute("SELECT count(*) FROM lore_pass_baselines")
            assert cur.fetchone()[0] == 0
            cur.execute(
                "SELECT count(*) FROM incubator WHERE session_id = %s", (session_id,)
            )
            assert cur.fetchone()[0] == 1

        with conn.cursor() as cur:
            cur.execute("DELETE FROM incubator WHERE session_id = %s", (session_id,))
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM incubator")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT count(*) FROM lore_pass_baselines")
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_missing_tail_error_and_admin_stamp_boundary(
    pass2_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Historical tails fail loudly until the explicit empty boundary is stamped."""

    database_url = f"postgresql://{os.environ.get('PGUSER', 'pythagor')}@"
    database_url += (
        f"{os.environ.get('PGHOST', 'localhost')}:"
        f"{os.environ.get('PGPORT', '5432')}/{pass2_database}"
    )
    engine = create_engine(database_url, future=True)
    conn = _connect(pass2_database)
    try:
        tail_chunk_id = _seed_parent(conn, "historical tail")
        conn.commit()
        manager = ContextMemoryManager(_settings(), memnon=_DatabaseMemnon(engine))
        with pytest.raises(
            MissingPass2BaselineError,
            match=r"scripts/stamp_lore_pass_baseline.py --slot <1-5>",
        ):
            manager.restore_pass2_baseline(tail_chunk_id)

        monkeypatch.setattr(
            stamp_lore_pass_baseline,
            "get_slot_db_url",
            lambda slot: database_url,
        )
        monkeypatch.setattr(
            stamp_lore_pass_baseline,
            "load_settings_as_dict",
            _settings,
        )
        assert stamp_lore_pass_baseline.stamp_slot_tail(5) == tail_chunk_id

        fresh = ContextMemoryManager(_settings(), memnon=_DatabaseMemnon(engine))
        restored = fresh.restore_pass2_baseline(tail_chunk_id)
        assert restored.parent_chunk_id == tail_chunk_id
        assert restored.memory_identities == []
        assert restored.prior_token_accounting == {}
        assert restored.remaining_budget == 0

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE lore_pass_baselines
                SET payload = jsonb_set(
                    payload,
                    '{config_fingerprint}',
                    to_jsonb(%s::text)
                )
                WHERE chunk_id = %s
                """,
                ("0" * 64, tail_chunk_id),
            )
        conn.commit()
        incompatible = ContextMemoryManager(_settings(), memnon=_DatabaseMemnon(engine))
        with pytest.raises(RuntimeError, match="config fingerprint is incompatible"):
            incompatible.restore_pass2_baseline(tail_chunk_id)
    finally:
        conn.close()
        engine.dispose()
