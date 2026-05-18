"""Tests for Orrery Bleed selector."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nexus.agents.lore.utils.turn_context import TurnContext
from nexus.agents.lore.utils.turn_cycle import TurnCycleManager
from nexus.agents.orrery.bleed import (
    BleedSelection,
    load_bleed_candidates,
    select_bleed_menu_async,
)


class FakeResult:
    """Tiny SQLAlchemy result stand-in."""

    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    """Session stand-in keyed by Bleed selector SQL markers."""

    def __init__(self, candidate_rows=None, max_chunk_id=100):
        self.candidate_rows = candidate_rows or []
        self.max_chunk_id = max_chunk_id
        self.executed = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append((sql, params))
        if "/* orrery:bleed_candidates */" in sql:
            assert "r.tick_chunk_id <= :anchor_chunk_id" in sql
            assert "r.offer_count < 3" in sql
            return FakeResult(self.candidate_rows)
        if "/* orrery:record_bleed_offers */" in sql:
            return FakeResult([])
        if "SELECT max(id) AS max_id" in sql:
            return FakeResult([{"max_id": self.max_chunk_id}])
        raise AssertionError(f"Unexpected Bleed query: {sql}")

    def commit(self):
        self.commits += 1


class FakeLLM:
    """Local LLM stand-in returning one Bleed selection."""

    def __init__(self, selection):
        self.selection = selection
        self.prompts = []

    async def structured_query_async(self, prompt, response_model, **_kwargs):
        self.prompts.append((prompt, response_model))
        return self.selection


class SlowLLM(FakeLLM):
    """Local LLM stand-in that exceeds the latency budget."""

    def __init__(self, selection):
        super().__init__(selection)
        self.cancelled = False

    async def structured_query_async(self, prompt, response_model, **kwargs):
        try:
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return await super().structured_query_async(prompt, response_model, **kwargs)


class FakeMemnon:
    """Minimal MEMNON stand-in exposing the Session factory."""

    def __init__(self, session):
        self.session = session

    def Session(self):
        return self.session


class FakeStoryResponse:
    """Minimal structured response stand-in for LOGON."""

    narrative = "Rain ticks against the glass."
    chunk_metadata = None
    referenced_entities = None
    state_updates = None


class FakeLogon:
    """LOGON stand-in returning a successful structured narrative."""

    async def generate_narrative_async(self, _payload):
        return FakeStoryResponse()


class FailingLogon:
    """LOGON stand-in that raises before a response is surfaced."""

    async def generate_narrative_async(self, _payload):
        raise RuntimeError("generation failed")


class FakeLore:
    """Minimal LORE stand-in for TurnCycleManager tests."""

    token_manager = None
    enable_logon = True

    def __init__(self, settings, session, llm_manager, logon=None):
        self.settings = settings
        self.memnon = FakeMemnon(session)
        self.llm_manager = llm_manager
        self.lazy_llm_manager = llm_manager
        self.ensure_llm_calls = 0
        self.logon = logon or FakeLogon()

    def ensure_logon(self):
        return None

    def _ensure_local_llm_manager(self):
        self.ensure_llm_calls += 1
        self.llm_manager = self.lazy_llm_manager
        return self.llm_manager


def _candidate_row():
    return {
        "resolution_id": 10,
        "narration_id": 501,
        "tick_chunk_id": 99,
        "template_id": "evade_pursuers",
        "event_type": "evade_pursuit",
        "actor_name": "Mara",
        "target_name": None,
        "perceptual_descriptor": {
            "channel": "digital",
            "summary": "street cameras briefly lose Mara",
            "brief": "Mara vanishes into a maintenance corridor.",
        },
        "brief": "Mara vanishes into a maintenance corridor.",
        "text": "Mara drops below the platform and vanishes from the cameras.",
        "magnitude": Decimal("0.720"),
    }


def _settings():
    return {
        "orrery": {
            "enabled": True,
            "bleed": {
                "latency_budget_ms": 2000,
                "max_candidates": 3,
                "candidate_pool_multiplier": 4,
            },
        }
    }


def test_load_bleed_candidates_coerces_descriptor() -> None:
    """Candidate loading keeps the Storyteller-facing descriptor separate."""

    candidates = load_bleed_candidates(
        FakeSession(candidate_rows=[_candidate_row()]),
        anchor_chunk_id=100,
        limit=3,
    )

    assert len(candidates) == 1
    assert candidates[0].resolution_id == 10
    assert candidates[0].channel == "digital"
    assert candidates[0].summary == "street cameras briefly lose Mara"
    assert candidates[0].magnitude == 0.72


@pytest.mark.asyncio
async def test_select_bleed_menu_returns_selected_without_recording_offers() -> None:
    """Selection is pure; offer bookkeeping waits until generation succeeds."""

    session = FakeSession(candidate_rows=[_candidate_row()])
    llm = FakeLLM(BleedSelection(selected_resolution_ids=[10], reasoning="apt"))

    result = await select_bleed_menu_async(
        session,
        llm_manager=llm,
        anchor_chunk_id=100,
        user_input="Continue.",
        warm_slice=[{"text": "Rain ticks against the transit glass."}],
        max_candidates=3,
        candidate_pool_multiplier=4,
        latency_budget_ms=2000,
    )

    assert result.candidates_considered == 1
    assert result.selected[0].resolution_id == 10
    assert session.commits == 0
    assert not any(
        "/* orrery:record_bleed_offers */" in sql for sql, _ in session.executed
    )


@pytest.mark.asyncio
async def test_select_bleed_menu_returns_empty_without_candidates() -> None:
    """No candidates means no local LLM call and no bookkeeping writes."""

    session = FakeSession(candidate_rows=[])
    llm = FakeLLM(BleedSelection(selected_resolution_ids=[10], reasoning="unused"))

    result = await select_bleed_menu_async(
        session,
        llm_manager=llm,
        anchor_chunk_id=100,
        user_input="Continue.",
        warm_slice=[],
        max_candidates=3,
        candidate_pool_multiplier=4,
        latency_budget_ms=2000,
    )

    assert result.candidates_considered == 0
    assert result.selected == []
    assert llm.prompts == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_select_bleed_menu_timeout_returns_empty() -> None:
    """Latency overruns produce an empty menu and no offer bookkeeping."""

    session = FakeSession(candidate_rows=[_candidate_row()])
    llm = SlowLLM(BleedSelection(selected_resolution_ids=[10]))

    result = await select_bleed_menu_async(
        session,
        llm_manager=llm,
        anchor_chunk_id=100,
        user_input="Continue.",
        warm_slice=[],
        max_candidates=3,
        candidate_pool_multiplier=4,
        latency_budget_ms=1,
    )

    assert result.timed_out is True
    assert result.selected == []
    assert llm.cancelled is True
    assert session.commits == 0


@pytest.mark.asyncio
async def test_select_bleed_menu_rejects_unknown_resolution_ids() -> None:
    """Hallucinated structured IDs fail loudly instead of silently disappearing."""

    session = FakeSession(candidate_rows=[_candidate_row()])

    with pytest.raises(ValueError, match="unknown resolutions"):
        await select_bleed_menu_async(
            session,
            llm_manager=FakeLLM(BleedSelection(selected_resolution_ids=[9999])),
            anchor_chunk_id=100,
            user_input="Continue.",
            warm_slice=[],
            max_candidates=3,
            candidate_pool_multiplier=4,
            latency_budget_ms=2000,
        )

    assert session.commits == 0


@pytest.mark.asyncio
async def test_assemble_context_payload_includes_bleed_menu() -> None:
    """LORE payload assembly injects selected ambient Orrery peripherals."""

    session = FakeSession(candidate_rows=[_candidate_row()])
    manager = TurnCycleManager(
        FakeLore(
            _settings(),
            session,
            FakeLLM(BleedSelection(selected_resolution_ids=[10], reasoning="apt")),
        )
    )
    context = TurnContext(
        turn_id="t1",
        user_input="Continue.",
        start_time=0,
        warm_slice=[{"id": 100, "text": "Rain ticks against the glass."}],
    )

    await manager.assemble_context_payload(context)

    assert context.phase_states["orrery_bleed"]["selected_count"] == 1
    assert context.context_payload["orrery_bleed_menu"][0]["summary"] == (
        "street cameras briefly lose Mara"
    )


@pytest.mark.asyncio
async def test_assemble_context_payload_initializes_bleed_llm_lazily() -> None:
    """Orrery Bleed may still opt into the legacy local manager on demand."""

    session = FakeSession(candidate_rows=[_candidate_row()])
    llm = FakeLLM(BleedSelection(selected_resolution_ids=[10], reasoning="apt"))
    lore = FakeLore(_settings(), session, llm)
    lore.llm_manager = None
    manager = TurnCycleManager(lore)
    context = TurnContext(
        turn_id="t1",
        user_input="Continue.",
        start_time=0,
        warm_slice=[{"id": 100, "text": "Rain ticks against the glass."}],
    )

    await manager.assemble_context_payload(context)

    assert lore.ensure_llm_calls == 1
    assert lore.llm_manager is llm
    assert context.phase_states["orrery_bleed"]["selected_count"] == 1


@pytest.mark.asyncio
async def test_assemble_context_payload_reuses_orrery_proposal_anchor() -> None:
    """Bleed uses the existing resolve anchor instead of recomputing max chunk."""

    session = FakeSession(candidate_rows=[_candidate_row()])
    manager = TurnCycleManager(
        FakeLore(
            _settings(),
            session,
            FakeLLM(BleedSelection(selected_resolution_ids=[10], reasoning="apt")),
        )
    )
    context = TurnContext(
        turn_id="t1",
        user_input="Continue.",
        start_time=0,
        warm_slice=[],
    )
    context.orrery_proposal = SimpleNamespace(anchor_chunk_id=77, pressure_count=0)

    await manager.assemble_context_payload(context)

    candidate_params = next(
        params
        for sql, params in session.executed
        if "/* orrery:bleed_candidates */" in sql
    )
    assert candidate_params["anchor_chunk_id"] == 77
    assert not any("SELECT max(id) AS max_id" in sql for sql, _ in session.executed)


@pytest.mark.asyncio
async def test_call_apex_ai_records_bleed_offers_after_generation_success() -> None:
    """Surfacing bookkeeping is written only after LOGON returns a response."""

    session = FakeSession()
    manager = TurnCycleManager(
        FakeLore(_settings(), session, FakeLLM(BleedSelection()), logon=FakeLogon())
    )
    context = TurnContext(turn_id="t1", user_input="Continue.", start_time=0)
    context.context_payload = {"user_input": "Continue."}
    context.bleed_menu = load_bleed_candidates(
        FakeSession(candidate_rows=[_candidate_row()]),
        anchor_chunk_id=100,
        limit=1,
    )
    context.phase_states["orrery_bleed"] = {
        "anchor_chunk_id": 100,
        "offers_recorded": 0,
    }

    response = await manager.call_apex_ai(context)
    update_params = next(
        params
        for sql, params in session.executed
        if "/* orrery:record_bleed_offers */" in sql
    )

    assert response.narrative == "Rain ticks against the glass."
    assert session.commits == 1
    assert update_params["resolution_ids"] == [10]
    assert context.phase_states["orrery_bleed"]["offers_recorded"] == 1


@pytest.mark.asyncio
async def test_call_apex_ai_does_not_record_bleed_offers_on_generation_failure() -> (
    None
):
    """Failed LOGON generation does not consume a Bleed opportunity."""

    session = FakeSession()
    manager = TurnCycleManager(
        FakeLore(_settings(), session, FakeLLM(BleedSelection()), logon=FailingLogon())
    )
    context = TurnContext(turn_id="t1", user_input="Continue.", start_time=0)
    context.context_payload = {"user_input": "Continue."}
    context.bleed_menu = load_bleed_candidates(
        FakeSession(candidate_rows=[_candidate_row()]),
        anchor_chunk_id=100,
        limit=1,
    )
    context.phase_states["orrery_bleed"] = {
        "anchor_chunk_id": 100,
        "offers_recorded": 0,
    }

    with pytest.raises(RuntimeError, match="generation failed"):
        await manager.call_apex_ai(context)

    assert session.commits == 0
    assert not any(
        "/* orrery:record_bleed_offers */" in sql for sql, _ in session.executed
    )
