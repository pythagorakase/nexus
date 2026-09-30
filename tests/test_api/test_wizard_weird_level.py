"""The genesis strangeness selection travels from the wizard to Retrograde (#838).

The selection is persisted on the wizard cache (``PUT /api/story/new/weird``
or the transition request), survives a failed transition, reaches
``perform_transition_with_retrograde`` and Retrograde generation, and the
resolved profile is recorded as genesis provenance in the world's transaction.
PostgreSQL, the model providers, and the embedding store are the external
boundaries replaced here; the real cache, schemas, routes, and guards run.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
from types import SimpleNamespace
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from nexus.api import (
    new_story_cache,
    new_story_flow,
    setup_endpoints,
    slot_endpoints,
    slot_mutations,
    slot_state,
    wizard_chat,
)
from nexus.api.narrative_schemas import (
    TransitionRequest,
    WeirdLevel,
    WeirdLevelRequest,
)
from nexus.api.new_story_cache import SuggestedTrait, WizardCache, _row_to_cache
from nexus.api.slot_state import SlotState, _get_wizard_state_from_row
from nexus.api.wizard_confirmation import WizardStateConflict
from tests.test_api.test_mock_wizard_responses import _fixture_rows

LEVELS: tuple[WeirdLevel, ...] = ("low", "medium", "high")


def ready_cache(**changes: Any) -> WizardCache:
    """The canned wizard, confirmed and complete, as the cache reader builds it."""
    row, trait_rows = _fixture_rows()
    row.update(thread_id="conv_ready", setting_confirmed=True, character_confirmed=True)
    selected = [
        SuggestedTrait(trait=r["name"], rationale=r["rationale"])
        for r in trait_rows
        if r["id"] <= 10
    ]
    cache = _row_to_cache(row, selected, len(selected), True, trait_rows[-1])
    assert cache.current_phase() == "ready"
    return replace(cache, **changes)


class WizardStore:
    """The wizard cache row behind the storage boundary, with a lock flag."""

    def __init__(self, cache: WizardCache | None, *, locked: bool = False) -> None:
        self.cache = cache
        self.locked = locked
        self.conflict = False
        self.events: list[tuple[str, Any]] = []

    def read(self, dbname: str) -> WizardCache | None:
        return self.cache

    @contextmanager
    def guard(self, dbname: str, expected: WizardCache) -> Iterator[None]:
        # The production guard compares the locked row with what the caller
        # read; a concurrent writer surfaces as WizardStateConflict.
        if self.conflict:
            raise WizardStateConflict(
                "The wizard changed while this response was being generated. "
                "Resume before retrying."
            )
        self.events.append(("guard", expected.weird_level))
        yield
        self.events.append(("commit", None))

    def write(self, dbname: str, level: WeirdLevel) -> None:
        assert self.events and self.events[-1][0] == "guard", "write outside guard"
        self.events.append(("write", level))
        assert self.cache is not None
        self.cache = replace(self.cache, weird_level=level)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> WizardStore:
    """Route the wizard routes' storage boundary to one in-memory row."""
    wizard = WizardStore(ready_cache())
    monkeypatch.setattr(
        slot_mutations, "is_slot_locked", lambda slot, dbname=None: wizard.locked
    )
    monkeypatch.setattr(wizard_chat, "read_cache", wizard.read)
    monkeypatch.setattr(wizard_chat, "guarded_wizard_write", wizard.guard)
    monkeypatch.setattr(wizard_chat, "write_weird_level", wizard.write)
    return wizard


@pytest.fixture
def client(store: WizardStore) -> TestClient:
    app = FastAPI()
    app.include_router(wizard_chat.router)
    return TestClient(app)


@pytest.fixture
def transitions(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture what the endpoint hands the (provider-calling) transition."""
    calls: list[dict[str, Any]] = []

    def perform(slot: int, transition_data: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"slot": slot, "world": transition_data.setting.world_name})
        calls[-1].update(kwargs)
        return {
            "character_id": 1,
            "place_id": 1,
            "layer_id": 1,
            "zone_id": 1,
            "retrograde": {"enabled": False, "skip_reason": "mock_wizard_model"},
            "trait_inputs": {"derived": False},
        }

    monkeypatch.setattr(wizard_chat, "perform_transition_with_retrograde", perform)
    return calls


# ── Request contracts ────────────────────────────────────────────────────


@pytest.mark.parametrize("level", LEVELS)
def test_requests_accept_each_level(level: WeirdLevel) -> None:
    assert WeirdLevelRequest(slot=4, weird_level=level).weird_level == level
    assert TransitionRequest(slot=4, weird_level=level).weird_level == level


@pytest.mark.parametrize("level", ["extreme", "HIGH", "", "0.9", 0.9, None])
def test_requests_reject_anything_but_the_three_levels(level: Any) -> None:
    with pytest.raises(ValidationError):
        WeirdLevelRequest(slot=4, weird_level=level)
    if level is not None:
        with pytest.raises(ValidationError):
            TransitionRequest(slot=4, weird_level=level)


@pytest.mark.parametrize("slot", [0, 6, "4", True])
def test_weird_request_requires_an_explicit_slot(slot: Any) -> None:
    with pytest.raises(ValidationError):
        WeirdLevelRequest(slot=slot, weird_level="low")


def test_transition_request_leaves_the_level_to_the_stored_selection() -> None:
    assert TransitionRequest(slot=4).weird_level is None


# ── PUT /api/story/new/weird ─────────────────────────────────────────────


@pytest.mark.parametrize("level", LEVELS)
def test_put_records_the_level_on_the_wizard_it_read(
    client: TestClient, store: WizardStore, level: WeirdLevel
) -> None:
    response = client.put(
        "/api/story/new/weird", json={"slot": 4, "weird_level": level}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "recorded", "slot": 4, "weird_level": level}
    assert store.events == [("guard", None), ("write", level), ("commit", None)]
    assert store.cache is not None and store.cache.weird_level == level


def test_put_refuses_a_locked_slot_before_reading_the_wizard(
    client: TestClient, store: WizardStore
) -> None:
    store.locked = True
    response = client.put(
        "/api/story/new/weird", json={"slot": 4, "weird_level": "high"}
    )
    assert response.status_code == 423
    assert store.events == []


def test_put_refuses_a_slot_without_a_wizard(
    client: TestClient, store: WizardStore
) -> None:
    store.cache = None
    response = client.put(
        "/api/story/new/weird", json={"slot": 4, "weird_level": "high"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "No active setup found for slot 4"
    assert store.events == []


@pytest.mark.parametrize(
    "body",
    [
        {"slot": 4, "weird_level": "extreme"},
        {"slot": 4},
        {"weird_level": "high"},
        {"slot": "4", "weird_level": "high"},
    ],
)
def test_put_rejects_an_invalid_request_without_writing(
    client: TestClient, store: WizardStore, body: dict[str, Any]
) -> None:
    response = client.put("/api/story/new/weird", json=body)
    assert response.status_code == 422
    assert store.events == []


def test_put_reports_a_concurrent_wizard_change_as_a_conflict(
    client: TestClient, store: WizardStore
) -> None:
    store.conflict = True
    response = client.put(
        "/api/story/new/weird", json={"slot": 4, "weird_level": "high"}
    )
    assert response.status_code == 409
    assert "Resume before retrying" in response.json()["detail"]
    assert store.cache is not None and store.cache.weird_level is None


# ── POST /api/story/new/transition ───────────────────────────────────────


@pytest.mark.asyncio
async def test_transition_persists_a_supplied_level_before_it_runs(
    store: WizardStore, transitions: list[dict[str, Any]]
) -> None:
    """A retry after a failed transition reads the level the first attempt saved."""
    store.cache = ready_cache(weird_level="low")

    response = await wizard_chat.transition_to_narrative_endpoint(
        TransitionRequest(slot=4, weird_level="high")
    )

    assert response.status == "transitioned"
    assert store.events == [("guard", "low"), ("write", "high"), ("commit", None)]
    assert transitions == [
        {"slot": 4, "world": "Neon Palimpsest", "weird_level": "high"}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", [*LEVELS, None])
async def test_transition_forwards_the_stored_selection(
    store: WizardStore, transitions: list[dict[str, Any]], stored: WeirdLevel | None
) -> None:
    """Without a supplied level the stored one runs; None means the default."""
    store.cache = ready_cache(weird_level=stored)

    await wizard_chat.transition_to_narrative_endpoint(TransitionRequest(slot=4))

    assert store.events == []
    assert [call["weird_level"] for call in transitions] == [stored]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "status", "detail"),
    [
        ({"setting_confirmed": False}, 409, "Confirm the setting and character"),
        ({"character_confirmed": False}, 409, "Confirm the setting and character"),
        ({"character_revision_pending": True}, 409, "Finish the character revision"),
        ({"base_timestamp": None}, 422, "Missing: base_timestamp"),
    ],
)
async def test_transition_guards_refuse_before_recording_a_level(
    store: WizardStore,
    transitions: list[dict[str, Any]],
    changes: dict[str, Any],
    status: int,
    detail: str,
) -> None:
    store.cache = ready_cache(**changes)
    with pytest.raises(HTTPException) as caught:
        await wizard_chat.transition_to_narrative_endpoint(
            TransitionRequest(slot=4, weird_level="high")
        )
    assert caught.value.status_code == status
    assert detail in caught.value.detail
    assert store.events == []
    assert transitions == []


@pytest.mark.asyncio
async def test_transition_refuses_an_incomplete_seed_before_recording_a_level(
    store: WizardStore, transitions: list[dict[str, Any]]
) -> None:
    cache = ready_cache()
    store.cache = replace(cache, seed=replace(cache.seed, zone_name=None))
    with pytest.raises(HTTPException) as caught:
        await wizard_chat.transition_to_narrative_endpoint(
            TransitionRequest(slot=4, weird_level="high")
        )
    assert caught.value.status_code == 422
    assert caught.value.detail == "Incomplete setup data. Missing: seed"
    assert store.events == []
    assert transitions == []


@pytest.mark.asyncio
async def test_transition_reports_a_concurrent_wizard_change_without_running(
    store: WizardStore, transitions: list[dict[str, Any]]
) -> None:
    store.conflict = True
    with pytest.raises(HTTPException) as caught:
        await wizard_chat.transition_to_narrative_endpoint(
            TransitionRequest(slot=4, weird_level="high")
        )
    assert caught.value.status_code == 409
    assert transitions == []


# ── Resume and slot state ────────────────────────────────────────────────


@pytest.mark.parametrize("stored", [*LEVELS, None])
def test_resume_restores_the_stored_selection(
    monkeypatch: pytest.MonkeyPatch, stored: WeirdLevel | None
) -> None:
    cache = ready_cache(weird_level=stored)
    monkeypatch.setattr(setup_endpoints, "resume_setup", lambda slot: cache)
    monkeypatch.setattr(setup_endpoints, "get_slot_model", lambda *a, **k: "saved")
    monkeypatch.setattr(
        setup_endpoints,
        "ConversationsClient",
        lambda model: SimpleNamespace(list_messages=lambda *a, **k: [], client=None),
    )
    app = FastAPI()
    app.include_router(setup_endpoints.router)

    data = TestClient(app).get("/api/story/new/setup/resume?slot=4").json()

    assert data["current_phase"] == "ready"
    assert data["weird_level"] == stored


@pytest.mark.parametrize("stored", [*LEVELS, None])
def test_slot_state_reports_the_stored_selection(
    monkeypatch: pytest.MonkeyPatch, stored: WeirdLevel | None
) -> None:
    row = {
        "thread_id": "conv_ready",
        "setting_genre": "cyberpunk",
        "setting_confirmed": True,
        "character_confirmed": True,
        "character_name": "Mara",
        "traits_confirmed": True,
        "wildcard_rationale": "The bell",
        "seed_type": "mystery",
        "layer_name": "Sprawl",
        "zone_name": "Undercity",
        "initial_location": {"name": "Gate"},
        "weird_level": stored,
    }
    wizard_state = _get_wizard_state_from_row(row)
    assert wizard_state.weird_level == stored

    state = SlotState(
        slot=4,
        is_empty=False,
        is_wizard_mode=True,
        wizard_state=wizard_state,
        narrative_state=None,
        model="saved",
    )
    monkeypatch.setattr(slot_state, "get_slot_state", lambda slot: state)
    monkeypatch.setattr(
        new_story_cache, "read_cache", lambda dbname: ready_cache(weird_level=stored)
    )
    app = FastAPI()
    app.include_router(slot_endpoints.router)

    data = TestClient(app).get("/api/slot/4/state").json()

    assert data["phase"] == "ready"
    assert data["weird_level"] == stored


def test_a_selection_change_does_not_void_an_in_flight_reply() -> None:
    """No wizard reply reads the level, so the reply fence ignores it."""
    before = ready_cache()
    after = replace(before, weird_level="high")
    assert new_story_cache._write_snapshot(before) == new_story_cache._write_snapshot(
        after
    )
    changed_seed = replace(before, seed=replace(before.seed, title="Another hook"))
    assert new_story_cache._write_snapshot(
        changed_seed
    ) != new_story_cache._write_snapshot(before)


def test_row_to_cache_reads_the_stored_selection() -> None:
    assert _row_to_cache({"weird_level": "medium"}).weird_level == "medium"
    assert _row_to_cache({}).weird_level is None


# ── perform_transition_with_retrograde ───────────────────────────────────


class RecordingCursor:
    """The transition transaction's cursor, recording the SQL it runs."""

    def __init__(self, rows_matched: int = 1) -> None:
        self.statements: list[tuple[str, Any]] = []
        self.rows_matched = rows_matched
        self.rowcount = -1

    def execute(self, sql: str, params: Any = None) -> None:
        self.statements.append((" ".join(sql.split()), params))
        self.rowcount = self.rows_matched


class TransactionMapper:
    """NewStoryDatabaseMapper at the database boundary: one open transaction."""

    cursor = RecordingCursor()

    def __init__(self, dbname: str) -> None:
        self.dbname = dbname

    def perform_transition(
        self, transition_data: Any, in_transaction: Any = None
    ) -> dict[str, int]:
        TransactionMapper.cursor = RecordingCursor()
        if in_transaction is not None:
            in_transaction(TransactionMapper.cursor)
        return {"character_id": 1, "layer_id": 1, "zone_id": 1, "place_id": 1}


GENESIS_SQL = "UPDATE global_variables SET genesis_weird = %s::jsonb WHERE id = TRUE"
# The database label the transition boundaries hand the fake mapper; no
# PostgreSQL connection is ever opened with it.
FAKE_DBNAME = "fake_transition_slot"


@pytest.fixture
def transition_boundaries(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace the slot database, providers, and embedding store only."""
    from nexus.agents.orrery import retrograde_orchestrator
    from nexus.api import new_story_db_mapper, save_slots, trait_input_derivation

    seen = SimpleNamespace(generation=[], persisted=[], slot_model=None)
    monkeypatch.setattr(
        save_slots, "get_slot_model", lambda slot, dbname=None: seen.slot_model
    )
    monkeypatch.setattr(
        new_story_db_mapper, "NewStoryDatabaseMapper", TransactionMapper
    )
    monkeypatch.setattr(new_story_flow, "slot_dbname", lambda slot: FAKE_DBNAME)
    monkeypatch.setattr(
        new_story_flow, "read_cache", lambda dbname: ready_cache(weird_level="high")
    )
    monkeypatch.setattr(
        trait_input_derivation,
        "ensure_trait_compile_inputs",
        lambda *a, **k: {"derived": False},
    )

    def generate(**kwargs: Any) -> Any:
        # The packet builder resolves the level through the genre's band.
        from nexus.agents.orrery.retrograde_packet import resolve_weird_profile

        seen.generation.append(kwargs)
        weird = resolve_weird_profile(
            settings=kwargs["settings"],
            setting={"genre": kwargs["cache"].setting.genre},
            weird_level=kwargs["weird_level"],
        )
        return SimpleNamespace(model="skald", weird=weird, timings=[])

    def persist(cur: Any, **kwargs: Any) -> dict[str, Any]:
        seen.persisted.append(len(cur.statements))
        cur.execute("INSERT INTO world_events DEFAULT VALUES")
        return {
            "counters": {},
            "entity_stub_budget": {},
            "retrieval": {"embedding_pending_summary_ids": []},
        }

    monkeypatch.setattr(
        retrograde_orchestrator, "generate_retrograde_history", generate
    )
    monkeypatch.setattr(retrograde_orchestrator, "persist_retrograde_history", persist)
    monkeypatch.setattr(
        retrograde_orchestrator,
        "embed_retrograde_history_summaries",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        retrograde_orchestrator,
        "build_wizard_history_surface",
        lambda **kwargs: {"weird_level": kwargs["bundle"].weird["level"]},
    )
    return seen


@pytest.mark.parametrize("level", [*LEVELS, None])
def test_transition_forwards_the_level_and_records_genesis_provenance(
    transition_boundaries: SimpleNamespace, level: WeirdLevel | None
) -> None:
    """The selected level reaches Retrograde and its band commits with history.

    The stored provenance keeps the level the wizard carried in
    (``selected_level``, null when the player chose none) beside the level
    Retrograde resolved, so a choice is distinguishable from the default.
    """
    from nexus.config import load_settings

    settings = load_settings()
    assert settings.orrery is not None
    weird_settings = settings.orrery.retrograde.weird
    expected_level = level or weird_settings.default_level
    band = getattr(weird_settings.bands_by_genre["cyberpunk"], expected_level)

    result = new_story_flow.perform_transition_with_retrograde(
        4,
        new_story_flow.build_transition_data_from_cache(ready_cache()),
        weird_level=level,
    )

    [generation] = transition_boundaries.generation
    assert generation["weird_level"] == level
    assert result["retrograde"]["weird"]["level"] == expected_level
    statements = TransactionMapper.cursor.statements
    # Provenance follows the history it describes on the same cursor.
    assert transition_boundaries.persisted == [0]
    assert statements[0][0] == "INSERT INTO world_events DEFAULT VALUES"
    assert statements[-1][0] == GENESIS_SQL
    provenance = json.loads(statements[-1][1][0])
    assert provenance == {**result["retrograde"]["weird"], "selected_level": level}
    assert provenance["selected_level"] == level
    assert provenance["level"] == expected_level
    assert provenance["genre"] == "cyberpunk"
    assert (provenance["raw_min"], provenance["raw_max"]) == (band.min, band.max)


def test_provenance_tells_the_default_apart_from_choosing_it(
    transition_boundaries: SimpleNamespace,
) -> None:
    """Choosing the default level and choosing nothing resolve alike but differ."""
    from nexus.config import load_settings

    settings = load_settings()
    assert settings.orrery is not None
    default_level = settings.orrery.retrograde.weird.default_level

    stored: list[dict[str, Any]] = []
    for selected in (default_level, None):
        new_story_flow.perform_transition_with_retrograde(
            4,
            new_story_flow.build_transition_data_from_cache(ready_cache()),
            weird_level=selected,
        )
        stored.append(json.loads(TransactionMapper.cursor.statements[-1][1][0]))

    chosen, defaulted = stored
    assert chosen["level"] == defaulted["level"] == default_level
    assert (chosen["selected_level"], defaulted["selected_level"]) == (
        default_level,
        None,
    )
    assert {**chosen, "selected_level": None} == defaulted


def test_a_story_without_retrograde_history_records_no_provenance(
    transition_boundaries: SimpleNamespace,
) -> None:
    """An overwritten slot cannot keep the previous story's provenance."""
    transition_boundaries.slot_model = new_story_flow.MOCK_WIZARD_MODEL

    result = new_story_flow.perform_transition_with_retrograde(
        4,
        new_story_flow.build_transition_data_from_cache(ready_cache()),
        weird_level="high",
    )

    assert result["retrograde"] == {
        "enabled": False,
        "skip_reason": "mock_wizard_model",
    }
    assert transition_boundaries.generation == []
    assert TransactionMapper.cursor.statements == [(GENESIS_SQL, (None,))]


def test_genesis_provenance_requires_the_global_variables_row() -> None:
    with pytest.raises(RuntimeError, match="no global_variables row"):
        new_story_flow._record_genesis_weird(
            RecordingCursor(rows_matched=0), {"level": "high"}, selected_level="high"
        )
