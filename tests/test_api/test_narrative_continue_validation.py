"""Route-level regression coverage for narrative continue validation."""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import psycopg2
import pytest
from fastapi.testclient import TestClient
from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor

from nexus.agents.logon.apex_schema import StorytellerResponseMinimal
from nexus.api import (
    chunk_workflow,
    db_pool,
    narrative,
    narrative_generation,
    narrative_lease,
    save_slots,
    slot_endpoints,
    slot_state,
)
from nexus.api.slot_state import NarrativeState, SlotState, WizardState
from nexus.config import get_available_api_models
from nexus.memory.manager import empty_pass2_baseline
from scripts import new_story_setup


TEST_BASELINE_PAYLOAD = empty_pass2_baseline({}).model_dump(mode="json")


@pytest.fixture(autouse=True)
def _unit_route_generation_lease(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep legacy transaction doubles focused outside PostgreSQL coverage."""
    if request.node.get_closest_marker("requires_postgres") is not None:
        return
    monkeypatch.setattr(
        narrative,
        "_acquire_generation_owner",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        narrative,
        "_bind_generation_owner",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr(
        narrative,
        "_abandon_generation_owner",
        lambda **_kwargs: None,
    )


class ChoiceCursor:
    """Serve one committed chunk through the production response resolver."""

    def __init__(self, connection: "ChoiceConnection") -> None:
        self.connection = connection
        self.result: dict[str, Any] | None = None
        self.rowcount = 0

    def __enter__(self) -> "ChoiceCursor":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, query: str, params: Any = None) -> None:
        normalized = " ".join(query.split())
        if "FROM incubator" in normalized:
            self.result = None
            return
        if "FROM narrative_chunks" in normalized and normalized.startswith("SELECT"):
            self.result = self.connection.chunk.copy()
            return
        if normalized.startswith("UPDATE"):
            self.connection.updates.append((normalized, params))
            self.rowcount = 1
            return
        raise AssertionError(f"Unexpected choice query: {normalized}")

    def fetchone(self) -> dict[str, Any] | None:
        return self.result


class ChoiceConnection:
    """Minimal transaction double for committed-choice route tests."""

    def __init__(self, chunk: dict[str, Any]) -> None:
        self.chunk = chunk
        self.updates: list[tuple[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self, **_kwargs: Any) -> ChoiceCursor:
        return ChoiceCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def _committed_state(*, choices: list[str]) -> SlotState:
    """Build the slot-state result returned by the production resolver."""
    return SlotState(
        slot=3,
        is_empty=False,
        is_wizard_mode=False,
        wizard_state=None,
        narrative_state=NarrativeState(
            current_chunk_id=17,
            has_pending=False,
            storyteller_text="The door waits.",
            choices=choices,
            session_id=None,
        ),
        model="existing-model",
    )


def _wizard_state() -> SlotState:
    """Build a wizard-mode slot state for route rejection coverage."""
    return SlotState(
        slot=3,
        is_empty=False,
        is_wizard_mode=True,
        wizard_state=WizardState(
            phase="setting",
            thread_id="wizard-thread",
            choices=[],
        ),
        narrative_state=None,
        model="existing-model",
    )


def _valid_override() -> str:
    """Return a configured concrete model accepted by the request schema."""
    return get_available_api_models()[0]


def _capture_model_writes(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture persistent model writes made by the route."""
    writes: list[dict[str, Any]] = []

    def capture(slot: int, **kwargs: Any) -> None:
        writes.append({"slot": slot, **kwargs})

    monkeypatch.setattr(save_slots, "upsert_slot", capture)
    return writes


def test_invalid_choice_does_not_persist_model_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Choice-range rejection precedes every canonical write."""
    choices = ["Open the door.", "Wait in silence."]
    connection = ChoiceConnection(
        {
            "id": 17,
            "storyteller_text": "The door waits.",
            "choice_object": {"presented": choices, "selected": None},
            "choice_text": None,
        }
    )
    monkeypatch.setattr(
        slot_state, "get_slot_state", lambda _slot: _committed_state(choices=choices)
    )
    monkeypatch.setattr(narrative, "get_db_connection", lambda _slot: connection)
    model_writes = _capture_model_writes(monkeypatch)

    response = TestClient(narrative.app).post(
        "/api/narrative/continue",
        json={"slot": 3, "choice": 99, "model": _valid_override()},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Choice 99 out of range (1-2)"
    assert model_writes == []
    assert connection.updates == []
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_conflicting_choice_and_accept_fate_does_not_persist_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mutually exclusive player inputs fail before slot mutation."""
    model_writes = _capture_model_writes(monkeypatch)

    response = TestClient(narrative.app).post(
        "/api/narrative/continue",
        json={
            "slot": 3,
            "choice": 1,
            "accept_fate": True,
            "model": _valid_override(),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot provide both choice and accept_fate"
    assert model_writes == []


def test_unresolved_committed_choices_require_player_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plain continue cannot skip an unresolved committed choice."""
    choices = ["Open the door.", "Wait in silence."]
    connection = ChoiceConnection(
        {
            "id": 17,
            "storyteller_text": "The door waits.",
            "choice_object": {"presented": choices, "selected": None},
            "choice_text": None,
        }
    )
    monkeypatch.setattr(
        slot_state, "get_slot_state", lambda _slot: _committed_state(choices=choices)
    )
    monkeypatch.setattr(narrative, "get_db_connection", lambda _slot: connection)
    model_writes = _capture_model_writes(monkeypatch)

    response = TestClient(narrative.app).post(
        "/api/narrative/continue",
        json={"slot": 3, "model": _valid_override()},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Current chunk has unresolved choices; provide choice, non-empty "
        "user_text, or accept_fate."
    )
    assert model_writes == []
    assert connection.updates == []


def test_wizard_mode_rejection_precedes_model_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even an explicit chunk cannot bypass slot-mode validation."""
    monkeypatch.setattr(slot_state, "get_slot_state", lambda _slot: _wizard_state())
    model_writes = _capture_model_writes(monkeypatch)

    response = TestClient(narrative.app).post(
        "/api/narrative/continue",
        json={"slot": 3, "chunk_id": 17, "model": _valid_override()},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Slot is in wizard mode. Use /api/story/new/chat for wizard."
    )
    assert model_writes == []


def test_choice_free_empty_continue_persists_override_and_starts_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Choice-free chunks retain deliberate empty-input continuation."""
    monkeypatch.setattr(
        slot_state, "get_slot_state", lambda _slot: _committed_state(choices=[])
    )
    model_writes = _capture_model_writes(monkeypatch)
    generation_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def capture_generation(*args: Any, **kwargs: Any) -> None:
        generation_calls.append((args, kwargs))

    monkeypatch.setattr(narrative, "generate_narrative_async", capture_generation)
    monkeypatch.setattr(
        narrative,
        "_trigger_locked_chunk_embedding",
        lambda **_kwargs: None,
    )

    response = TestClient(narrative.app).post(
        "/api/narrative/continue",
        json={"slot": 3, "model": _valid_override()},
    )

    assert response.status_code == 200
    assert model_writes == [
        {
            "slot": 3,
            "model": _valid_override(),
            "dbname": "save_03",
        }
    ]
    assert len(generation_calls) == 1
    generation_args, _generation_kwargs = generation_calls[0]
    assert generation_args[1:4] == (17, "", 3)


def test_explicit_slotless_chunk_with_unresolved_choices_requires_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicitly addressed chunk cannot bypass the unresolved-choice guard."""
    choices = ["Open the door.", "Wait in silence."]
    connection = ChoiceConnection(
        {
            "id": 17,
            "storyteller_text": "The door waits.",
            "choice_object": {"presented": choices, "selected": None},
            "choice_text": None,
        }
    )
    monkeypatch.setattr(narrative, "get_db_connection", lambda _slot: connection)
    model_writes = _capture_model_writes(monkeypatch)

    response = TestClient(narrative.app).post(
        "/api/narrative/continue",
        json={"chunk_id": 17},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Current chunk has unresolved choices; provide choice, non-empty "
        "user_text, or accept_fate."
    )
    assert model_writes == []
    assert connection.updates == []


def test_explicit_slotless_choice_free_chunk_keeps_empty_continue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A choice-free explicitly addressed chunk retains empty-input continuation."""
    connection = ChoiceConnection(
        {
            "id": 17,
            "storyteller_text": "The road runs on.",
            "choice_object": None,
            "choice_text": None,
        }
    )
    monkeypatch.setattr(narrative, "get_db_connection", lambda _slot: connection)
    model_writes = _capture_model_writes(monkeypatch)
    generation_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def capture_generation(*args: Any, **kwargs: Any) -> None:
        generation_calls.append((args, kwargs))

    monkeypatch.setattr(narrative, "generate_narrative_async", capture_generation)
    monkeypatch.setattr(
        narrative,
        "_trigger_locked_chunk_embedding",
        lambda **_kwargs: None,
    )

    response = TestClient(narrative.app).post(
        "/api/narrative/continue",
        json={"chunk_id": 17},
    )

    assert response.status_code == 200
    assert model_writes == []
    assert len(generation_calls) == 1
    generation_args, _generation_kwargs = generation_calls[0]
    assert generation_args[1:3] == (17, "")


def _connect(dbname: str, *, dict_cursor: bool = False) -> Any:
    """Open a direct PostgreSQL connection for a disposable clone."""
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        cursor_factory=RealDictCursor if dict_cursor else None,
    )


def _seed_protagonist(dbname: str) -> None:
    """Bind the disposable save to a canonical player character."""

    with _connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE global_variables SET base_timestamp = %s WHERE id = true",
                ("2100-01-01T00:00:00+00:00",),
            )
            assert cur.rowcount == 1
            cur.execute(
                "INSERT INTO entities (kind, is_active) "
                "VALUES ('character', true) RETURNING id"
            )
            entity_id = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO characters (name, summary, entity_id)
                VALUES ('Continue Fixture Player', %s, %s)
                RETURNING id
                """,
                ("Canonical player for narrative continue coverage.", entity_id),
            )
            character_id = int(cur.fetchone()[0])
            cur.execute(
                "UPDATE global_variables SET user_character = %s WHERE id = true",
                (character_id,),
            )
            assert cur.rowcount == 1


@pytest.fixture()
def disposable_narrative_db() -> Iterator[str]:
    """Yield an initialized disposable save and drop it afterward."""
    dbname = f"nexus_test_continue_{uuid.uuid4().hex[:12]}"
    admin: Any = None
    original_use_pool = new_story_setup.USE_POOL
    try:
        try:
            admin = _connect("postgres")
        except psycopg2.Error as exc:
            pytest.skip(f"PostgreSQL admin connection unavailable: {exc}")
        admin.autocommit = True
        new_story_setup.USE_POOL = False
        new_story_setup.initialize_slot_database(
            dbname,
            source_db="NEXUS_template",
        )
        _seed_protagonist(dbname)
        yield dbname
    finally:
        new_story_setup.USE_POOL = original_use_pool
        pool = db_pool._pools.pop(dbname, None)
        if pool is not None:
            pool.closeall()
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


@contextmanager
def _clone_connection(dbname: str, *, dict_cursor: bool = False) -> Iterator[Any]:
    """Match the production pooled-connection transaction contract."""
    conn = _connect(dbname, dict_cursor=dict_cursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _route_clone_to_slot(monkeypatch: pytest.MonkeyPatch, dbname: str) -> None:
    """Route production slot/database helpers to one disposable clone."""
    monkeypatch.setattr(slot_state, "slot_dbname", lambda _slot: dbname)
    monkeypatch.setattr(
        slot_state,
        "get_connection",
        lambda _dbname, dict_cursor=False: _clone_connection(
            dbname, dict_cursor=dict_cursor
        ),
    )
    monkeypatch.setattr(narrative, "get_db_connection", lambda _slot: _connect(dbname))


def _reset_to_committed_parent(dbname: str) -> int:
    """Reset a clone to one playable committed parent and return its id."""
    with _clone_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE incubator, narrative_chunks,
                    narrative_generation_lease,
                    narrative_parent_embedding_claims,
                    narrative_generation_sessions
                RESTART IDENTITY CASCADE
                """
            )
            cur.execute("DELETE FROM assets.new_story_creator")
            cur.execute(
                """
                INSERT INTO narrative_chunks (
                    raw_text, storyteller_text, state
                ) VALUES (%s, %s, 'finalized')
                RETURNING id
                """,
                ("The platform waits.", "The platform waits."),
            )
            parent_chunk_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO chunk_metadata (
                    chunk_id, season, episode, scene, world_layer, slug
                ) VALUES (%s, 1, 1, 1, 'primary', 'S01E01_001')
                """,
                (parent_chunk_id,),
            )
    return int(parent_chunk_id)


class ImmediateLore:
    """Frontier-only success double for genuine route/DB pipeline tests."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.settings_path = Path("test-settings.toml")
        self.turn_context = SimpleNamespace(
            error_log=[],
            memory_state={"lore_pass_baseline": TEST_BASELINE_PAYLOAD},
            orrery_proposal=None,
        )

    async def process_turn(
        self,
        user_text: str,
        parent_chunk_id: int,
        note: str | None = None,
    ) -> StorytellerResponseMinimal:
        return StorytellerResponseMinimal(
            generation_model="route-lease-fixture",
            narrative="A single train enters the station.",
            choices=["Board it.", "Let it pass."],
        )

    def close(self) -> None:
        return None


@pytest.mark.requires_postgres
def test_concurrent_continues_have_one_owner_and_truthful_result(
    monkeypatch: pytest.MonkeyPatch,
    disposable_narrative_db: str,
) -> None:
    """Concurrent calls serialize and notification failure cannot corrupt success."""
    dbname = disposable_narrative_db
    parent_chunk_id = _reset_to_committed_parent(dbname)

    _route_clone_to_slot(monkeypatch, dbname)
    entered_generation = threading.Event()
    release_generation = threading.Event()
    embedding_calls: list[int] = []

    class BlockingLore:
        """Frontier-only double; route, DB reads, adapter, and writer stay real."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.settings_path = Path("test-settings.toml")
            self.turn_context = SimpleNamespace(
                error_log=[],
                memory_state={"lore_pass_baseline": TEST_BASELINE_PAYLOAD},
                orrery_proposal=None,
            )

        async def process_turn(
            self,
            user_text: str,
            parent_chunk_id: int,
            note: str | None = None,
        ) -> StorytellerResponseMinimal:
            entered_generation.set()
            released = await asyncio.to_thread(release_generation.wait, 10)
            if not released:
                raise RuntimeError("Timed out waiting to release generation fixture")
            return StorytellerResponseMinimal(
                generation_model="route-concurrency-fixture",
                narrative="A single train enters the station.",
                choices=["Board it.", "Let it pass."],
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(narrative_generation, "LORE", BlockingLore)
    monkeypatch.setattr(
        narrative,
        "_trigger_locked_chunk_embedding",
        lambda *, slot, parent_chunk_id: embedding_calls.append(parent_chunk_id),
    )
    original_send_progress = narrative.manager.send_progress

    async def fail_completed_broadcast(
        session_id: str,
        status: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        if status == "complete":
            raise RuntimeError("stale WebSocket fixture")
        await original_send_progress(session_id, status, data)

    monkeypatch.setattr(
        narrative.manager,
        "send_progress",
        fail_completed_broadcast,
    )

    def post_continue() -> Any:
        with TestClient(narrative.app) as client:
            return client.post(
                "/api/narrative/continue",
                json={"slot": 3},
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner_future = executor.submit(post_continue)
        assert entered_generation.wait(10), "owner never reached storyteller generation"
        competitor = post_continue()
        release_generation.set()
        owner = owner_future.result(timeout=15)

    assert owner.status_code == 200
    owner_session_id = owner.json()["session_id"]
    assert competitor.status_code == 409
    assert competitor.json()["detail"] == {
        "message": "Another narrative generation owns this slot.",
        "active_session_id": owner_session_id,
    }
    assert embedding_calls == [parent_chunk_id]

    with _clone_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT session_id, parent_chunk_id, chunk_id
                FROM incubator
                """
            )
            incubator = cur.fetchone()
            assert incubator == {
                "session_id": owner_session_id,
                "parent_chunk_id": parent_chunk_id,
                "chunk_id": parent_chunk_id + 1,
            }
            cur.execute("SELECT COUNT(*) AS count FROM narrative_generation_lease")
            assert cur.fetchone()["count"] == 0

            cur.execute(
                """
                SELECT session_id, status, parent_chunk_id, chunk_id
                FROM narrative_generation_sessions
                """
            )
            sessions = cur.fetchall()
            assert sessions == [
                {
                    "session_id": owner_session_id,
                    "status": "complete",
                    "parent_chunk_id": parent_chunk_id,
                    "chunk_id": parent_chunk_id + 1,
                }
            ]
            cur.execute(
                """
                SELECT parent_chunk_id, session_id
                FROM narrative_parent_embedding_claims
                """
            )
            assert cur.fetchall() == [
                {
                    "parent_chunk_id": parent_chunk_id,
                    "session_id": owner_session_id,
                }
            ]

    with _connect(dbname) as conn:
        with pytest.raises(RuntimeError, match="refusing error downgrade"):
            narrative_lease.finish_generation(
                conn,
                session_id=owner_session_id,
                status="error",
                error="late notification failure",
            )

    with TestClient(narrative.app) as client:
        status = client.get(
            f"/api/narrative/status/{owner_session_id}",
            params={"slot": 3},
        )
        cleared = client.delete(
            "/api/narrative/incubator",
            params={"slot": 3},
        )
        unloaded_status = client.get(
            f"/api/narrative/status/{owner_session_id}",
            params={"slot": 3},
        )
    assert status.status_code == 200
    assert status.json()["status"] == "complete"
    assert status.json()["chunk_id"] == parent_chunk_id + 1
    assert cleared.status_code == 200
    assert unloaded_status.status_code == 200
    assert unloaded_status.json()["status"] == "error"
    assert unloaded_status.json()["chunk_id"] is None
    assert unloaded_status.json()["error"] == (
        "Completed result is no longer loadable for this session."
    )


@pytest.mark.requires_postgres
def test_errored_embedding_claim_is_reclaimed_and_scheduled(
    monkeypatch: pytest.MonkeyPatch,
    disposable_narrative_db: str,
) -> None:
    """A retry replaces an errored owner's orphan claim and schedules work."""
    dbname = disposable_narrative_db
    parent_chunk_id = _reset_to_committed_parent(dbname)
    crashed_session_id = str(uuid.uuid4())
    with _connect(dbname) as conn:
        assert (
            narrative_lease.acquire_generation_lease(
                conn,
                session_id=crashed_session_id,
                operation="continue",
                stale_timeout_seconds=60,
            )
            is None
        )
        narrative_lease.bind_generation_parent(
            conn,
            session_id=crashed_session_id,
            parent_chunk_id=parent_chunk_id,
        )
        assert narrative_lease.claim_parent_embedding(
            conn,
            session_id=crashed_session_id,
            parent_chunk_id=parent_chunk_id,
        )
        narrative_lease.finish_generation(
            conn,
            session_id=crashed_session_id,
            status="error",
            error="Simulated crash after durable claim.",
        )

    _route_clone_to_slot(monkeypatch, dbname)
    monkeypatch.setattr(narrative_generation, "LORE", ImmediateLore)
    embedding_calls: list[int] = []
    monkeypatch.setattr(
        narrative,
        "_trigger_locked_chunk_embedding",
        lambda *, slot, parent_chunk_id: embedding_calls.append(parent_chunk_id),
    )

    with TestClient(narrative.app) as client:
        response = client.post("/api/narrative/continue", json={"slot": 3})

    assert response.status_code == 200
    retry_session_id = response.json()["session_id"]
    assert embedding_calls == [parent_chunk_id]
    with _clone_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT session_id
                FROM narrative_parent_embedding_claims
                WHERE parent_chunk_id = %s
                """,
                (parent_chunk_id,),
            )
            assert str(cur.fetchone()["session_id"]) == retry_session_id


@pytest.mark.requires_postgres
def test_live_embedding_claim_cannot_be_stolen(
    monkeypatch: pytest.MonkeyPatch,
    disposable_narrative_db: str,
) -> None:
    """A retry pipeline cannot replace a claim whose owner remains live."""
    dbname = disposable_narrative_db
    parent_chunk_id = _reset_to_committed_parent(dbname)
    live_session_id = str(uuid.uuid4())
    with _connect(dbname) as conn:
        assert (
            narrative_lease.acquire_generation_lease(
                conn,
                session_id=live_session_id,
                operation="continue",
                stale_timeout_seconds=60,
            )
            is None
        )
        narrative_lease.bind_generation_parent(
            conn,
            session_id=live_session_id,
            parent_chunk_id=parent_chunk_id,
        )
        assert narrative_lease.claim_parent_embedding(
            conn,
            session_id=live_session_id,
            parent_chunk_id=parent_chunk_id,
        )
        with conn.cursor() as cur:
            # Simulate loss of the mutex without falsely terminalizing the
            # session: its durable status remains live/initiated.
            cur.execute(
                """
                DELETE FROM narrative_generation_lease
                WHERE session_id = %s
                """,
                (live_session_id,),
            )
        conn.commit()

    _route_clone_to_slot(monkeypatch, dbname)
    monkeypatch.setattr(narrative_generation, "LORE", ImmediateLore)
    embedding_calls: list[int] = []
    monkeypatch.setattr(
        narrative,
        "_trigger_locked_chunk_embedding",
        lambda *, slot, parent_chunk_id: embedding_calls.append(parent_chunk_id),
    )

    with TestClient(narrative.app) as client:
        response = client.post("/api/narrative/continue", json={"slot": 3})

    assert response.status_code == 200
    assert embedding_calls == []
    with _clone_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT session_id
                FROM narrative_parent_embedding_claims
                WHERE parent_chunk_id = %s
                """,
                (parent_chunk_id,),
            )
            assert str(cur.fetchone()["session_id"]) == live_session_id


@pytest.mark.requires_postgres
def test_pre_scheduling_failure_releases_embedding_claim(
    monkeypatch: pytest.MonkeyPatch,
    disposable_narrative_db: str,
) -> None:
    """Abandoning after claim but before task scheduling leaves no orphan."""
    dbname = disposable_narrative_db
    _reset_to_committed_parent(dbname)
    _route_clone_to_slot(monkeypatch, dbname)

    async def fail_initiated_broadcast(
        session_id: str,
        status: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        raise RuntimeError("pre-scheduling notification fixture")

    monkeypatch.setattr(
        narrative.manager,
        "send_progress",
        fail_initiated_broadcast,
    )

    with TestClient(narrative.app, raise_server_exceptions=False) as client:
        response = client.post("/api/narrative/continue", json={"slot": 3})

    assert response.status_code == 500
    with _clone_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM narrative_generation_lease")
            assert cur.fetchone()["count"] == 0
            cur.execute(
                "SELECT COUNT(*) AS count FROM narrative_parent_embedding_claims"
            )
            assert cur.fetchone()["count"] == 0
            cur.execute("SELECT status FROM narrative_generation_sessions")
            assert cur.fetchall() == [{"status": "error"}]


@pytest.mark.requires_postgres
def test_pending_incubator_session_mismatch_is_409(
    monkeypatch: pytest.MonkeyPatch,
    disposable_narrative_db: str,
) -> None:
    """A stale state read cannot fall through past another incubator owner."""
    dbname = disposable_narrative_db
    parent_chunk_id = _reset_to_committed_parent(dbname)
    expected_session_id = str(uuid.uuid4())
    actual_session_id = str(uuid.uuid4())
    choices = ["Open the door.", "Wait in silence."]
    with _clone_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO incubator (
                    id, chunk_id, parent_chunk_id, user_text, storyteller_text,
                    generation_model, choice_object, choice_text,
                    metadata_updates, entity_updates, reference_updates,
                    orrery_proposal, orrery_adjudications, new_entities,
                    lore_pass_baseline, session_id, llm_response_id, status
                ) VALUES (
                    TRUE, %s, %s, %s, %s, %s, %s, NULL,
                    %s, %s, %s, NULL, %s, %s, %s, %s, %s, 'provisional'
                )
                """,
                (
                    parent_chunk_id + 1,
                    parent_chunk_id,
                    "Approach the door.",
                    "The hinges begin to move.",
                    _valid_override(),
                    Json({"presented": choices, "selected": None}),
                    Json({}),
                    Json({}),
                    Json({"characters": [], "places": [], "factions": []}),
                    Json([]),
                    Json([]),
                    Json(TEST_BASELINE_PAYLOAD),
                    expected_session_id,
                    "session-mismatch-fixture",
                ),
            )

    _route_clone_to_slot(monkeypatch, dbname)
    production_get_slot_state = slot_state.get_slot_state
    changed_owner = False

    def stale_slot_state(slot: int) -> SlotState:
        nonlocal changed_owner
        state = production_get_slot_state(slot)
        if not changed_owner:
            with _clone_connection(dbname) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE incubator
                        SET session_id = %s
                        WHERE session_id = %s
                        """,
                        (actual_session_id, expected_session_id),
                    )
            changed_owner = True
        return state

    monkeypatch.setattr(slot_state, "get_slot_state", stale_slot_state)
    with TestClient(narrative.app) as client:
        response = client.post(
            "/api/narrative/continue",
            json={"slot": 3, "choice": 1},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": f"Incubator session mismatch for chunk {parent_chunk_id + 1}.",
        "expected_session_id": expected_session_id,
        "actual_session_id": actual_session_id,
    }


@pytest.mark.requires_postgres
def test_pending_choice_rolls_back_when_auto_approval_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
    disposable_narrative_db: str,
) -> None:
    """The real pending continue route makes choice resolution and approval atomic."""
    dbname = disposable_narrative_db
    choices = ["Open the door.", "Wait in silence."]
    pending_session_id = str(uuid.uuid4())
    with _clone_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE incubator, narrative_chunks,
                    narrative_generation_lease,
                    narrative_parent_embedding_claims,
                    narrative_generation_sessions
                RESTART IDENTITY CASCADE
                """
            )
            cur.execute("DELETE FROM assets.new_story_creator")
            cur.execute(
                """
                INSERT INTO narrative_chunks (
                    raw_text, storyteller_text, state
                ) VALUES (%s, %s, 'finalized')
                RETURNING id
                """,
                ("The door waits.", "The door waits."),
            )
            parent_chunk_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO chunk_metadata (
                    chunk_id, season, episode, scene, world_layer, slug
                ) VALUES (%s, 1, 1, 1, 'primary', 'S01E01_001')
                """,
                (parent_chunk_id,),
            )
            cur.execute(
                """
                INSERT INTO incubator (
                    id, chunk_id, parent_chunk_id, user_text, storyteller_text,
                    generation_model, choice_object, choice_text,
                    metadata_updates, entity_updates, reference_updates,
                    orrery_proposal, orrery_adjudications, new_entities,
                    lore_pass_baseline, session_id, llm_response_id, status
                ) VALUES (
                    TRUE, %s, %s, %s, %s, %s, %s, NULL,
                    %s, %s, %s, NULL, %s, %s, %s, %s, %s, 'provisional'
                )
                """,
                (
                    parent_chunk_id + 1,
                    parent_chunk_id,
                    "Approach the door.",
                    "The hinges begin to move.",
                    _valid_override(),
                    Json({"presented": choices, "selected": None}),
                    Json(
                        {
                            "chronology": {"episode_transition": "invalid-transition"},
                            "world_layer": "primary",
                        }
                    ),
                    Json({}),
                    Json({"characters": [], "places": [], "factions": []}),
                    Json([]),
                    Json([]),
                    Json(TEST_BASELINE_PAYLOAD),
                    pending_session_id,
                    "invalid-approval-fixture",
                ),
            )

    _route_clone_to_slot(monkeypatch, dbname)
    with TestClient(narrative.app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/narrative/continue",
            json={"slot": 3, "choice": 1},
        )

    assert response.status_code == 500
    with _clone_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT choice_text, choice_object
                FROM incubator
                WHERE session_id = %s
                """,
                (pending_session_id,),
            )
            pending = cur.fetchone()
            assert pending == {
                "choice_text": None,
                "choice_object": {"presented": choices, "selected": None},
            }
            cur.execute("SELECT COUNT(*) AS count FROM narrative_chunks")
            assert cur.fetchone()["count"] == 1
            cur.execute("SELECT COUNT(*) AS count FROM narrative_generation_lease")
            assert cur.fetchone()["count"] == 0

    # Simulate the carried finding's already-in-the-wild recovery state: an
    # earlier request committed the choice before approval failed. The same
    # choice must be reusable without a conflict, and real approval must commit.
    with _clone_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE incubator
                SET choice_text = %s,
                    choice_object = %s,
                    metadata_updates = %s
                WHERE session_id = %s
                """,
                (
                    choices[0],
                    Json({"presented": choices, "selected": 1}),
                    Json(
                        {
                            "chronology": {
                                "episode_transition": "continue",
                                "time_delta_minutes": 1,
                            },
                            "world_layer": "primary",
                        }
                    ),
                    pending_session_id,
                ),
            )

    async def stop_after_approval(
        session_id: str,
        _parent_chunk_id: int,
        _user_text: str,
        slot: int,
        **_kwargs: Any,
    ) -> None:
        narrative._abandon_generation_owner(
            slot=slot,
            session_id=session_id,
            error="Fixture stops after proving approval recovery.",
        )

    monkeypatch.setattr(narrative, "generate_narrative_async", stop_after_approval)
    monkeypatch.setattr(
        narrative,
        "_run_post_commit_orrery_work",
        lambda _slot: None,
    )
    with TestClient(narrative.app) as client:
        recovered = client.post(
            "/api/narrative/continue",
            json={"slot": 3, "choice": 1},
        )

    assert recovered.status_code == 200
    with _clone_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT choice_text, choice_object
                FROM narrative_chunks
                ORDER BY id DESC
                LIMIT 1
                """
            )
            committed = cur.fetchone()
            assert committed == {
                "choice_text": choices[0],
                "choice_object": {"presented": choices, "selected": 1},
            }


@pytest.mark.requires_postgres
def test_undo_restores_unresolved_parent_and_plain_continue_rejects(
    monkeypatch: pytest.MonkeyPatch,
    disposable_narrative_db: str,
) -> None:
    """The real undo→continue path cannot advance without a player decision."""
    dbname = disposable_narrative_db
    choices = ["Open the door.", "Wait in silence."]
    storyteller_text = "The door waits."
    selected_text = choices[0]
    session_id = str(uuid.uuid4())

    with _clone_connection(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE incubator, narrative_chunks RESTART IDENTITY CASCADE")
            cur.execute("DELETE FROM assets.new_story_creator")
            cur.execute(
                """
                INSERT INTO narrative_chunks (
                    raw_text, storyteller_text, choice_object, choice_text, state
                ) VALUES (%s, %s, %s, %s, 'finalized')
                RETURNING id
                """,
                (
                    f"{storyteller_text}\n\n{selected_text}",
                    storyteller_text,
                    Json({"presented": choices, "selected": 1}),
                    selected_text,
                ),
            )
            parent_chunk_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO incubator (
                    id, chunk_id, parent_chunk_id, user_text, storyteller_text,
                    generation_model, choice_object, choice_text,
                    metadata_updates, entity_updates, reference_updates,
                    orrery_proposal, orrery_adjudications, new_entities,
                    session_id, llm_response_id, status
                ) VALUES (
                    TRUE, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    parent_chunk_id + 1,
                    parent_chunk_id,
                    selected_text,
                    "The hinges sigh open.",
                    _valid_override(),
                    Json({"presented": ["Enter."], "selected": None}),
                    None,
                    Json({}),
                    Json({}),
                    Json({}),
                    None,
                    Json([]),
                    Json([]),
                    session_id,
                    "test-response",
                    "complete",
                ),
            )

    monkeypatch.setattr(slot_state, "slot_dbname", lambda _slot: dbname)
    monkeypatch.setattr(
        slot_state,
        "get_connection",
        lambda _dbname, dict_cursor=False: _clone_connection(
            dbname, dict_cursor=dict_cursor
        ),
    )
    monkeypatch.setattr(slot_endpoints, "slot_dbname", lambda _slot: dbname)
    monkeypatch.setattr(
        slot_endpoints,
        "get_connection",
        lambda _dbname, dict_cursor=False: _clone_connection(
            dbname, dict_cursor=dict_cursor
        ),
    )
    monkeypatch.setattr(chunk_workflow, "VALID_DATABASES", {dbname})
    monkeypatch.setattr(
        chunk_workflow,
        "get_connection",
        lambda _dbname, dict_cursor=False: _clone_connection(
            dbname, dict_cursor=dict_cursor
        ),
    )
    monkeypatch.setattr(narrative, "get_db_connection", lambda _slot: _connect(dbname))
    generation_calls: list[tuple[Any, ...]] = []

    async def capture_generation(*args: Any, **_kwargs: Any) -> None:
        generation_calls.append(args)

    monkeypatch.setattr(narrative, "generate_narrative_async", capture_generation)

    with TestClient(narrative.app) as client:
        undo_response = client.post("/api/slot/3/undo")
        continue_response = client.post(
            "/api/narrative/continue",
            json={"slot": 3},
        )

    assert undo_response.status_code == 200
    assert undo_response.json()["success"] is True
    assert continue_response.status_code == 400
    assert continue_response.json()["detail"] == (
        "Current chunk has unresolved choices; provide choice, non-empty "
        "user_text, or accept_fate."
    )
    assert generation_calls == []

    with _clone_connection(dbname, dict_cursor=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM incubator")
            assert cur.fetchone()["count"] == 0
            cur.execute(
                """
                SELECT raw_text, storyteller_text, choice_text, choice_object
                FROM narrative_chunks
                WHERE id = %s
                """,
                (parent_chunk_id,),
            )
            parent = cur.fetchone()
            assert parent["raw_text"] == storyteller_text
            assert parent["storyteller_text"] == storyteller_text
            assert parent["choice_text"] is None
            assert parent["choice_object"] == {
                "presented": choices,
                "selected": None,
            }
