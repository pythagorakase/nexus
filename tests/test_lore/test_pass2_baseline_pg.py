"""Ephemeral-PostgreSQL lifecycle coverage for durable Pass-2 baselines."""

from __future__ import annotations

import asyncio
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import psycopg2
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from nexus.agents.lore.logon_utility import LogonUtility
from nexus.agents.lore.lore import LORE
from nexus.agents.logon.apex_schema import StorytellerResponseStandard
from nexus.api import commit_handler, commit_handler_sync
from nexus.api.commit_handler_sync import commit_incubator_to_database_sync
from nexus.api.lore_adapter import response_to_incubator
from nexus.api.narrative_generation import generate_narrative_async, write_to_incubator
from nexus.config import load_settings_as_dict
from nexus.memory.context_state import bind_pass2_baseline
from nexus.memory.manager import (
    ContextMemoryManager,
    MissingPass2BaselineError,
    empty_pass2_baseline,
)
from scripts import stamp_lore_pass_baseline
from tests.pg_fixtures import disposable_slot_database, seed_protagonist


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
    """Initialize the template, reapply migration 107, and drop the clone."""

    source_db = os.environ.get("NEXUS_TEST_TEMPLATE_DB", "NEXUS_template")
    with disposable_slot_database("nexus_test_pass2", source_db=source_db) as dbname:
        migration = MIGRATION.read_text()
        with _connect(dbname) as conn:
            with conn.cursor() as cur:
                # Migration 107 remains deliberately double-applied to prove
                # idempotency against the current, fully migrated template.
                cur.execute(migration)
                cur.execute(migration)
                cur.execute("DELETE FROM incubator")
                cur.execute("DELETE FROM narrative_generation_lease")
                cur.execute("DELETE FROM narrative_generation_sessions")
        seed_protagonist(
            dbname,
            name="Pass Two Fixture Player",
            summary="Canonical player for Pass-2 lifecycle coverage.",
        )
        yield dbname


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
        self.Session = sessionmaker(bind=engine)
        self.idf_dictionary = None
        self.results = results or []

    def query_memory(
        self, query: str, k: int = 5, use_hybrid: bool = True
    ) -> dict[str, Any]:
        del query, k, use_hybrid
        return {"results": copy.deepcopy(self.results)}

    def get_chunk_by_id(self, chunk_id: int) -> dict[str, Any] | None:
        """Load one real narrative row for LORE's warm-slice anchor."""

        with self.db_manager.engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT id, raw_text, storyteller_text "
                        "FROM narrative_chunks WHERE id = :chunk_id"
                    ),
                    {"chunk_id": chunk_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        prose = row["storyteller_text"] or row["raw_text"] or ""
        return {
            "id": row["id"],
            "chunk_id": row["id"],
            "text": prose,
            "full_text": prose,
        }

    def get_recent_chunks(self, limit: int = 10) -> dict[str, Any]:
        """Load real recent narrative rows for LORE's warm slice."""

        with self.db_manager.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, raw_text, storyteller_text FROM narrative_chunks "
                    "ORDER BY id DESC LIMIT :limit"
                ),
                {"limit": limit},
            ).mappings()
            results = [
                {
                    "id": row["id"],
                    "chunk_id": row["id"],
                    "text": row["storyteller_text"] or row["raw_text"] or "",
                }
                for row in rows
            ]
        return {"results": results}

    def close(self) -> None:
        """Leave the test-owned shared engine alive across fresh LORE instances."""


class _RouteProvider:
    """Structured-output provider stub used beneath a real LogonUtility."""

    def __init__(self, outputs: list[dict[str, Any]]) -> None:
        self.model = "gpt-4o"
        self.system_prompt = "Pass-2 lifecycle provider stub"
        self.outputs = outputs
        self.calls: list[dict[str, Any]] = []

    async def get_structured_completion_async(
        self,
        prompt: str,
        schema_model: Any,
        **kwargs: Any,
    ) -> tuple[Any, object]:
        """Validate the queued payload through LOGON's selected wire schema."""

        self.calls.append(
            {"prompt": prompt, "schema_model": schema_model, "kwargs": kwargs}
        )
        if not self.outputs:
            raise AssertionError("Provider stub exhausted")
        return schema_model.model_validate(self.outputs.pop(0)), object()


class _ProgressRecorder:
    """Record the real narrative route's progress notifications."""

    def __init__(self) -> None:
        self.statuses: list[str] = []

    async def send_progress(
        self,
        session_id: str,
        status: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Capture one route notification without an external WebSocket."""

        del session_id, data
        self.statuses.append(status)


def _wire_payload(narrative: str) -> dict[str, Any]:
    return {
        "narrative": narrative,
        "choices": ["Continue.", "Wait."],
        "orrery_adjudications": [],
        "new_entities": [],
        "letter": "Preserve the current continuity while advancing the scene.",
    }


async def _connect_async(dbname: str) -> asyncpg.Connection:
    conn = await asyncpg.connect(
        database=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
    )
    for type_name in ("json", "jsonb"):
        await conn.set_type_codec(
            type_name,
            schema="pg_catalog",
            encoder=json.dumps,
            decoder=json.loads,
        )
    return conn


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


def test_real_continuation_route_restores_pass2_baseline_in_fresh_lore(
    pass2_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production continuation route hydrates Pass 2 across fresh LOREs."""

    _patch_unrelated_commit_work(monkeypatch)
    route_settings = load_settings_as_dict()
    route_settings["orrery"]["enabled"] = False
    route_settings["API Settings"]["apex"]["turn_pipeline"] = "single_pass"
    route_settings["apex"]["turn_pipeline"] = "single_pass"

    database_url = f"postgresql://{os.environ.get('PGUSER', 'pythagor')}@"
    database_url += (
        f"{os.environ.get('PGHOST', 'localhost')}:"
        f"{os.environ.get('PGPORT', '5432')}/{pass2_database}"
    )
    engine = create_engine(database_url, future=True)
    conn = _connect(pass2_database)
    lore_instances: list[LORE] = []
    provider_outputs = [
        _wire_payload("Turn N provider prose."),
        _wire_payload("Turn N plus one provider prose."),
    ]
    providers: list[_RouteProvider] = []
    retrieval_id = 999_998
    new_retrieval_id = 999_999
    retrieval_batches = [
        [{"chunk_id": retrieval_id, "text": "turn N retrieved memory"}],
        [
            {"chunk_id": retrieval_id, "text": "duplicate turn N memory"},
            {"chunk_id": new_retrieval_id, "text": "new turn N+1 memory"},
        ],
    ]
    memnon_count = 0

    original_init = LORE.__init__

    def load_route_settings(
        lore: LORE, settings_path: str | None = None
    ) -> dict[str, Any]:
        del settings_path
        lore.settings_path = Path("nexus.toml").resolve()
        return copy.deepcopy(route_settings)

    def initialize_route_memnon(lore: LORE) -> None:
        nonlocal memnon_count
        if memnon_count >= len(retrieval_batches):
            raise AssertionError("Unexpected extra LORE instance")
        lore.memnon = _DatabaseMemnon(engine, retrieval_batches[memnon_count])
        memnon_count += 1

    def initialize_route_logon(lore: LORE) -> None:
        utility = LogonUtility(
            lore.settings,
            dbname=pass2_database,
            settings_path=lore.settings_path,
            model_override="gpt-4o",
        )
        utility._setting_context_loaded = True
        utility._setting_context = None
        provider = _RouteProvider(provider_outputs)
        utility.provider = provider
        utility._provider_bootstrap_mode = False
        utility._provider_wire_type = "openai"
        utility._provider_type_name = "openai"
        utility._system_prompt = provider.system_prompt
        lore.logon = utility
        lore._logon_initialized = True
        providers.append(provider)

    def record_lore_instance(lore: LORE, *args: Any, **kwargs: Any) -> None:
        original_init(lore, *args, **kwargs)
        lore_instances.append(lore)

    monkeypatch.setattr(LORE, "_load_settings", load_route_settings)
    monkeypatch.setattr(LORE, "_initialize_memnon", initialize_route_memnon)
    monkeypatch.setattr(LORE, "_initialize_logon", initialize_route_logon)
    monkeypatch.setattr(LORE, "__init__", record_lore_instance)
    monkeypatch.setattr(
        LogonUtility,
        "_format_turn_tag_library",
        lambda _self, _context, *, presence_baseline: "",
    )

    try:
        parent_chunk_id = _seed_parent(conn, "route parent")
        retrieval_batches[1].insert(
            0,
            {"chunk_id": parent_chunk_id, "text": "duplicate turn N parent"},
        )
        explicit_bootstrap_boundary = bind_pass2_baseline(
            empty_pass2_baseline(route_settings), parent_chunk_id
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lore_pass_baselines (chunk_id, schema_version, payload)
                VALUES (%s, %s, %s::jsonb)
                """,
                (
                    parent_chunk_id,
                    explicit_bootstrap_boundary.schema_version,
                    json.dumps(explicit_bootstrap_boundary.model_dump(mode="json")),
                ),
            )
        first_session = str(uuid4())
        _create_lease(conn, first_session, parent_chunk_id)
        conn.commit()

        first_progress = _ProgressRecorder()
        asyncio.run(
            generate_narrative_async(
                first_session,
                parent_chunk_id,
                "Investigate Zyxonium.",
                slot=5,
                get_db_connection=lambda _slot: _connect(pass2_database),
                load_settings=lambda: copy.deepcopy(route_settings),
                manager=first_progress,
                manage_generation_lease=False,
            )
        )
        assert first_progress.statuses[-1] == "complete"
        assert len(lore_instances) == 1
        assert (
            lore_instances[0].turn_context.memory_state["pass2"]["baseline_available"]
            is True
        )
        staged_first = lore_instances[0].turn_context.memory_state["lore_pass_baseline"]
        assert parent_chunk_id in staged_first["memory_identities"]
        assert retrieval_id in staged_first["memory_identities"]

        accepted_chunk_id = commit_incubator_to_database_sync(
            conn, first_session, slot=5
        )

        second_session = str(uuid4())
        _replace_lease(conn, second_session, accepted_chunk_id)
        conn.commit()
        second_progress = _ProgressRecorder()
        asyncio.run(
            generate_narrative_async(
                second_session,
                accepted_chunk_id,
                "Investigate Zyxonium again.",
                slot=5,
                get_db_connection=lambda _slot: _connect(pass2_database),
                load_settings=lambda: copy.deepcopy(route_settings),
                manager=second_progress,
                manage_generation_lease=False,
            )
        )

        assert second_progress.statuses[-1] == "complete"
        assert len(lore_instances) == 2
        assert lore_instances[0] is not lore_instances[1]
        pass2_state = lore_instances[1].turn_context.memory_state["pass2"]
        assert pass2_state["baseline_available"] is True
        assert pass2_state["retrieved_memory_ids"] == [new_retrieval_id]
        assert parent_chunk_id not in pass2_state["retrieved_memory_ids"]
        assert retrieval_id not in pass2_state["retrieved_memory_ids"]
        assert sum(len(provider.calls) for provider in providers) == 2

        with conn.cursor() as cur:
            cur.execute(
                "SELECT lore_pass_baseline FROM incubator WHERE session_id = %s",
                (second_session,),
            )
            second_staged = cur.fetchone()[0]
        assert new_retrieval_id in second_staged["memory_identities"]
    finally:
        conn.close()
        engine.dispose()


def test_component_regeneration_sparse_promotion_restore_and_cascade(
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


@pytest.mark.asyncio
async def test_async_regeneration_replace_and_acceptance_failure_roll_back(
    pass2_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Async promotion atomically preserves the replacement draft on failure."""

    sync_conn = _connect(pass2_database)
    async_conn: asyncpg.Connection | None = None
    try:
        parent_chunk_id = _seed_parent(sync_conn, "async rollback parent")
        first_session = str(uuid4())
        _create_lease(sync_conn, first_session, parent_chunk_id)
        sync_conn.commit()

        first_manager = ContextMemoryManager(_settings())
        first_manager.handle_storyteller_response(
            narrative="Async first candidate.",
            warm_slice=[{"chunk_id": parent_chunk_id, "text": "parent"}],
            token_usage={"total_available": 50, "warm_slice": 10},
        )
        first_payload = response_to_incubator(
            _response("Async first candidate."),
            parent_chunk_id=parent_chunk_id,
            user_text="Continue.",
            session_id=first_session,
            lore_pass_baseline=first_manager.export_pass2_baseline(),
        )
        await write_to_incubator(sync_conn, first_payload)

        replacement_memory_id = 999_997
        replacement_manager = ContextMemoryManager(_settings())
        replacement_manager.handle_storyteller_response(
            narrative="Async replacement candidate.",
            warm_slice=[
                {"chunk_id": parent_chunk_id, "text": "parent"},
                {"chunk_id": replacement_memory_id, "text": "replacement memory"},
            ],
            token_usage={"total_available": 50, "warm_slice": 12},
        )
        replacement_session = str(uuid4())
        _replace_lease(sync_conn, replacement_session, parent_chunk_id)
        sync_conn.commit()
        replacement_payload = response_to_incubator(
            _response("Async replacement candidate."),
            parent_chunk_id=parent_chunk_id,
            user_text="Continue again.",
            session_id=replacement_session,
            lore_pass_baseline=replacement_manager.export_pass2_baseline(),
        )
        await write_to_incubator(
            sync_conn,
            replacement_payload,
            expected_incubator_session=first_session,
        )

        with sync_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM narrative_chunks")
            before_chunks = int(cur.fetchone()[0])
            cur.execute(
                "SELECT storyteller_text, session_id, lore_pass_baseline "
                "FROM incubator"
            )
            staged_text, staged_session, staged_baseline = cur.fetchone()
        assert staged_text == "Async replacement candidate."
        assert staged_session == replacement_session
        assert replacement_memory_id in staged_baseline["memory_identities"]

        async def fail_metadata(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("forced async metadata failure")

        monkeypatch.setattr(commit_handler, "insert_chunk_metadata", fail_metadata)
        async_conn = await _connect_async(pass2_database)
        with pytest.raises(RuntimeError, match="forced async metadata failure"):
            await commit_handler.commit_incubator_to_database(
                async_conn, replacement_session, slot=5
            )

        assert (
            await async_conn.fetchval("SELECT count(*) FROM narrative_chunks")
            == before_chunks
        )
        assert (
            await async_conn.fetchval("SELECT count(*) FROM lore_pass_baselines") == 0
        )
        preserved = await async_conn.fetchrow(
            "SELECT storyteller_text, session_id, lore_pass_baseline " "FROM incubator"
        )
        assert preserved is not None
        assert preserved["storyteller_text"] == "Async replacement candidate."
        assert str(preserved["session_id"]) == replacement_session
        assert (
            replacement_memory_id
            in preserved["lore_pass_baseline"]["memory_identities"]
        )
    finally:
        if async_conn is not None:
            await async_conn.close()
        sync_conn.close()


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
        stamped_chunk_id, tail_stamped, incubator_stamped = (
            stamp_lore_pass_baseline.stamp_slot_tail(5)
        )
        assert stamped_chunk_id == tail_chunk_id
        assert tail_stamped is True
        assert incubator_stamped is False

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
