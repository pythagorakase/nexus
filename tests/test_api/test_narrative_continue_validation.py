"""Route-level regression coverage for narrative continue validation."""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
import pytest
from fastapi.testclient import TestClient
from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor

from nexus.api import chunk_workflow, narrative, save_slots, slot_endpoints, slot_state
from nexus.api.slot_state import NarrativeState, SlotState, WizardState
from nexus.config import get_available_api_models


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


def _connect(dbname: str, *, dict_cursor: bool = False) -> Any:
    """Open a direct PostgreSQL connection for a disposable clone."""
    return psycopg2.connect(
        dbname=dbname,
        user=os.environ.get("PGUSER", "pythagor"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        cursor_factory=RealDictCursor if dict_cursor else None,
    )


@pytest.fixture()
def disposable_narrative_db() -> Iterator[str]:
    """Yield an isolated NEXUS_template clone and drop it afterward."""
    dbname = f"nexus_test_continue_{uuid.uuid4().hex[:12]}"
    admin = None
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
                    sql.Identifier("NEXUS_template"),
                )
            )
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
